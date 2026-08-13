"""Stage 06 — dispatch the validated protocol to an OT-2 over the HTTP Runs API.

Two pieces:
  OT2Client   — speaks the REAL Opentrons robot-server Runs API
                (POST /protocols -> POST /runs -> POST /runs/{id}/actions{play}
                 -> poll GET /runs/{id}). Point `base_url` at a real OT-2 (:31950)
                 and this same client drives real hardware.
  VirtualOT2  — a simulated robot-server that speaks that same API and runs the
                uploaded protocol through `opentrons analyze` under the hood, so
                dispatch can be demonstrated end-to-end with no hardware.

Per the LABA design, actuation is gated on human sign-off; the demo flag makes
that explicit. This module never runs a protocol on real hardware unless you
point it at a real robot URL yourself.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Callable

import httpx

from .simulate import analyze

_HEADERS = {"Opentrons-Version": "3"}


# --------------------------------------------------------------------------- #
# Client — the real Runs-API shape
# --------------------------------------------------------------------------- #
class OT2Client:
    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base = base_url.rstrip("/")
        self._c = httpx.Client(timeout=timeout, headers=_HEADERS)

    def health(self) -> dict:
        return self._c.get(f"{self.base}/health").json()

    def upload_protocol(self, path: str | Path) -> str:
        p = Path(path)
        with p.open("rb") as f:
            r = self._c.post(f"{self.base}/protocols",
                             files={"files": (p.name, f, "text/x-python")})
        r.raise_for_status()
        return r.json()["data"]["id"]

    def protocol_analysis(self, protocol_id: str) -> dict:
        return self._c.get(f"{self.base}/protocols/{protocol_id}").json()["data"].get("analysis", {})

    def create_run(self, protocol_id: str) -> str:
        r = self._c.post(f"{self.base}/runs", json={"data": {"protocolId": protocol_id}})
        r.raise_for_status()
        return r.json()["data"]["id"]

    def action(self, run_id: str, action_type: str) -> None:
        r = self._c.post(f"{self.base}/runs/{run_id}/actions",
                         json={"data": {"actionType": action_type}})
        r.raise_for_status()

    def run_status(self, run_id: str) -> dict:
        return self._c.get(f"{self.base}/runs/{run_id}").json()["data"]

    def run_to_completion(self, path: str | Path, *,
                          on_event: Callable[[str, dict], None] | None = None,
                          poll_s: float = 0.4, max_polls: int = 40) -> dict:
        def emit(kind: str, **d):
            if on_event:
                on_event(kind, d)

        h = self.health()
        emit("health", name=h.get("name"), model=h.get("robot_model"), api=h.get("api_version"))
        pid = self.upload_protocol(path)
        analysis = self.protocol_analysis(pid)
        emit("uploaded", protocol_id=pid, analysis=analysis)
        rid = self.create_run(pid)
        emit("run_created", run_id=rid)
        self.action(rid, "play")
        emit("play", run_id=rid)
        status = "idle"
        for _ in range(max_polls):
            data = self.run_status(rid)
            status = data.get("status", "unknown")
            emit("status", run_id=rid, status=status, commands=data.get("commandCount"))
            if status in ("succeeded", "failed", "stopped"):
                break
            time.sleep(poll_s)
        return {"run_id": rid, "status": status, "protocol_id": pid, "analysis": analysis}

    def close(self):
        self._c.close()


# --------------------------------------------------------------------------- #
# Virtual robot — same API, backed by opentrons analyze
# --------------------------------------------------------------------------- #
def _extract_uploaded_file(raw: bytes, content_type: str) -> str:
    if "boundary=" not in content_type:
        return raw.decode("utf-8", "replace")
    boundary = ("--" + content_type.split("boundary=")[1]).encode()
    for part in raw.split(boundary):
        head, _, body = part.partition(b"\r\n\r\n")
        if b"filename=" in head and body:
            return body.rsplit(b"\r\n", 1)[0].decode("utf-8", "replace")
    return raw.decode("utf-8", "replace")


def _make_handler(state: dict, workdir: Path, run_seconds: float):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # silence
            pass

        def _send(self, code: int, obj: dict):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                return self._send(200, {"name": "virtual-ot2", "api_version": "2.20",
                                        "robot_model": "OT-2 Standard (simulated)"})
            if self.path.startswith("/protocols/"):
                pid = self.path.split("/")[2]
                p = state["protocols"].get(pid)
                return self._send(200 if p else 404, {"data": p} if p else {"errors": ["not found"]})
            if self.path.startswith("/runs/"):
                rid = self.path.split("/")[2]
                r = state["runs"].get(rid)
                if not r:
                    return self._send(404, {"errors": ["run not found"]})
                if r["status"] == "running" and time.time() - r["_play_at"] >= run_seconds:
                    r["status"] = "succeeded" if r["_ok"] else "failed"
                return self._send(200, {"data": {k: v for k, v in r.items() if not k.startswith("_")}})
            return self._send(404, {"errors": ["not found"]})

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(n) if n else b""
            if self.path == "/protocols":
                src = _extract_uploaded_file(raw, self.headers.get("Content-Type", ""))
                pid = "proto-" + uuid.uuid4().hex[:8]
                path = workdir / f"{pid}.py"
                path.write_text(src)
                res = analyze(path)
                state["protocols"][pid] = {"id": pid, "path": str(path),
                                           "analysis": {"result": res.result,
                                                        "errors": len(res.errors),
                                                        "commandCount": res.n_commands}}
                return self._send(201, {"data": state["protocols"][pid]})
            if self.path == "/runs":
                data = json.loads(raw or b"{}").get("data", {})
                proto = state["protocols"].get(data.get("protocolId"), {})
                rid = "run-" + uuid.uuid4().hex[:8]
                state["runs"][rid] = {
                    "id": rid, "protocolId": data.get("protocolId"), "status": "idle",
                    "commandCount": proto.get("analysis", {}).get("commandCount", 0),
                    "_ok": proto.get("analysis", {}).get("result") == "ok", "_play_at": 0.0}
                return self._send(201, {"data": {k: v for k, v in state["runs"][rid].items()
                                                 if not k.startswith("_")}})
            if self.path.startswith("/runs/") and self.path.endswith("/actions"):
                rid = self.path.split("/")[2]
                r = state["runs"].get(rid)
                if not r:
                    return self._send(404, {"errors": ["run not found"]})
                act = json.loads(raw or b"{}").get("data", {}).get("actionType", "play")
                if act == "play":
                    r["status"] = "running"
                    r["_play_at"] = time.time()
                elif act == "stop":
                    r["status"] = "stopped"
                return self._send(201, {"data": {"actionType": act}})
            return self._send(404, {"errors": ["not found"]})

    return Handler


class VirtualOT2:
    """A simulated OT-2 robot-server. `with VirtualOT2() as url: ...`"""

    def __init__(self, workdir: str | Path | None = None, run_seconds: float = 0.8):
        self.state = {"protocols": {}, "runs": {}}
        self.workdir = Path(workdir) if workdir else Path(__file__).resolve().parents[2] / \
            "examples" / "chemotaxis_penstrep" / "out" / "virtual_ot2"
        self.workdir.mkdir(parents=True, exist_ok=True)
        self._server = HTTPServer(("127.0.0.1", 0),
                                  _make_handler(self.state, self.workdir, run_seconds))
        self.port = self._server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self) -> str:
        self._thread.start()
        return self.url

    def stop(self):
        self._server.shutdown()
        self._server.server_close()

    def __enter__(self) -> str:
        return self.start()

    def __exit__(self, *a):
        self.stop()


def dispatch_to_virtual(protocol_path: str | Path,
                        on_event: Callable[[str, dict], None] | None = None) -> dict:
    """Spin up a simulated OT-2, dispatch the protocol over the real Runs API, tear down."""
    robot = VirtualOT2()
    url = robot.start()
    try:
        client = OT2Client(url)
        result = client.run_to_completion(protocol_path, on_event=on_event)
        client.close()
        result["robot_url"] = url
        return result
    finally:
        robot.stop()
