"""Stage 06 dispatch: the Runs-API client drives a simulated OT-2 to succeeded,
and a bad protocol reaches failed. Localhost only (no external network)."""
import time
from pathlib import Path

from paper2protocol.dispatch import OT2Client, VirtualOT2, dispatch_to_virtual

FIX = Path(__file__).parent / "fixtures"


def test_dispatch_good_succeeds():
    r = dispatch_to_virtual(FIX / "good_dilution.py")
    assert r["status"] == "succeeded"
    assert r["analysis"]["result"] == "ok"
    assert r["analysis"]["commandCount"] > 0


def test_dispatch_bad_fails():
    r = dispatch_to_virtual(FIX / "bad_overaspirate.py")
    assert r["status"] == "failed"


def test_client_lifecycle_over_runs_api():
    with VirtualOT2(run_seconds=0.1) as url:
        c = OT2Client(url)
        assert "ot2" in c.health()["name"]
        pid = c.upload_protocol(FIX / "good_dilution.py")
        rid = c.create_run(pid)
        c.action(rid, "play")
        status = "idle"
        for _ in range(30):
            status = c.run_status(rid)["status"]
            if status in ("succeeded", "failed"):
                break
            time.sleep(0.1)
        assert status == "succeeded"
        c.close()
