"""Stage 5b — the real judge: wrap `opentrons analyze` and parse its output.

Locked to the M1-captured contract (opentrons 8.8.2), NOT to the research brief
(which was wrong about the invocation, the version, and the error shape):

  invocation : python -m opentrons.cli analyze --json-output - [--check]
               [--rtp-values '{...}'] PROTOCOL.py [labware.json ...]
  result     : "ok" | "not-ok" | "parameter-value-required"
  exit(check): 0 on ok, 255 on not-ok
  errors[]   : ErrorOccurrence with keys
               {id, createdAt, isDefined, errorType, errorCode, detail,
                errorInfo, wrappedErrors}
               - top errorType is a wrapper (e.g. ExceptionInProtocolError);
                 the ROOT cause is the deepest wrappedErrors entry, and it
                 carries a structured errorInfo (e.g. attempted_aspirate_volume).
               - the protocol line number appears in `detail` as "[line N]".

This module has ZERO authority over acceptance; it only reports. `loop.py`
decides converged/blocked from these facts.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# analyze is a SUBCOMMAND of the opentrons.cli click group (verified M1).
_ANALYZE_CMD = [sys.executable, "-m", "opentrons.cli", "analyze"]
_LINE_RE = re.compile(r"\[line (\d+)\]")
_ALT_LINE_RE = re.compile(r'line (\d+)')


@dataclass
class ParsedError:
    """One analyze error, flattened to what the repair loop needs."""

    top_type: str            # top-level errorType (usually a wrapper)
    root_type: str           # deepest wrappedErrors errorType (the real cause)
    error_code: str          # 4-digit band; 4000s = protocol/API misuse
    line: int | None         # protocol line, parsed from detail "[line N]"
    detail: str              # full human message (root cause's, most specific)
    error_info: dict         # structured root-cause info (volumes, etc.)

    def signature(self) -> str:
        """Stable identity for oscillation detection (loop.py).

        Deliberately excludes volatile ids/timestamps. Same bug -> same string.
        """
        return f"{self.root_type}|{self.error_code}|L{self.line}"

    def hint(self) -> str:
        """A compact correction hint fed back to the generator."""
        loc = f" at line {self.line}" if self.line else ""
        extra = ""
        if self.error_info:
            extra = " | info: " + ", ".join(f"{k}={v}" for k, v in self.error_info.items())
        return f"{self.root_type} (code {self.error_code}){loc}: {self.detail}{extra}"


@dataclass
class AnalyzeResult:
    result: str | None           # "ok" | "not-ok" | "parameter-value-required" | None
    exit_code: int
    errors: list[ParsedError]
    n_commands: int
    commands: list = field(default_factory=list, repr=False)  # for conformance (Stage 5c)
    raw: dict = field(default_factory=dict, repr=False)
    stderr_tail: str = ""

    @property
    def ok(self) -> bool:
        return self.result == "ok" and not self.errors

    @property
    def needs_params(self) -> bool:
        return self.result == "parameter-value-required"

    def error_signatures(self) -> set[str]:
        return {e.signature() for e in self.errors}


def _deepest(err: dict) -> dict:
    """Walk wrappedErrors to the root-cause error object."""
    cur = err
    while cur.get("wrappedErrors"):
        cur = cur["wrappedErrors"][0]
    return cur


def _parse_line(text: str) -> int | None:
    m = _LINE_RE.search(text or "")
    if m:
        return int(m.group(1))
    m = _ALT_LINE_RE.search(text or "")
    return int(m.group(1)) if m else None


def _parse_error(err: dict) -> ParsedError:
    root = _deepest(err)
    # prefer the line number from whichever detail carries it
    line = _parse_line(err.get("detail", "")) or _parse_line(root.get("detail", ""))
    return ParsedError(
        top_type=err.get("errorType", "?"),
        root_type=root.get("errorType", err.get("errorType", "?")),
        error_code=str(err.get("errorCode", root.get("errorCode", ""))),
        line=line,
        detail=root.get("detail") or err.get("detail") or "",
        error_info=root.get("errorInfo") or {},
    )


def analyze(
    protocol_path: str | Path,
    *,
    rtp_values: dict | None = None,
    custom_labware: list[str | Path] | None = None,
    check: bool = True,
    timeout: int = 180,
) -> AnalyzeResult:
    """Run `opentrons analyze` on a protocol and return a parsed result.

    Runs on virtual hardware — no robot, no calibration, and modules/pipettes
    not physically owned still validate.
    """
    cmd = list(_ANALYZE_CMD) + ["--json-output", "-"]
    if check:
        cmd.append("--check")
    if rtp_values:
        cmd += ["--rtp-values", json.dumps(rtp_values)]
    cmd.append(str(protocol_path))
    cmd += [str(p) for p in (custom_labware or [])]

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    parsed = _extract_json(proc.stdout)
    errors = [_parse_error(e) for e in parsed.get("errors", [])]
    return AnalyzeResult(
        result=parsed.get("result"),
        exit_code=proc.returncode,
        errors=errors,
        n_commands=len(parsed.get("commands", [])),
        commands=parsed.get("commands", []),
        raw=parsed,
        stderr_tail="\n".join(proc.stderr.strip().splitlines()[-4:]),
    )


def _extract_json(stdout: str) -> dict:
    if stdout and "{" in stdout:
        try:
            return json.loads(stdout[stdout.index("{"):])
        except json.JSONDecodeError:
            return {}
    return {}
