"""M1 — Empirically capture the REAL `opentrons analyze` contract.

The panel flagged every asserted CLI/version fact as unverified. This script
runs the actually-installed opentrons build and records:
  - opentrons version, MAX_SUPPORTED_VERSION, python version
  - the canonical analyze invocation + whether it warns
  - exit codes WITH and WITHOUT --check, on good and bad protocols
  - the AnalyzeResults JSON shape (result enum, top-level keys)
  - the ErrorOccurrence field set (the object the repair loop parses)
  - which labware load-names + pipettes actually exist in the library

Outputs (captured/):
  - <fixture>.analysis.json         golden analyze JSON, parser locked to these
  - analyze_contract.json           the machine-readable captured contract
  - analyze_contract.md             human-readable summary

Run:  uv run python scripts/capture_contract.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures"
OUT = ROOT / "captured"
OUT.mkdir(exist_ok=True)

# labware / pipette names our design relies on — verify they exist
LABWARE = [
    "opentrons_96_tiprack_300ul",
    "opentrons_96_tiprack_20ul",
    "opentrons_96_tiprack_1000ul",
    "nest_12_reservoir_15ml",
    "corning_24_wellplate_3.4ml_flat",
    "corning_12_wellplate_6.9ml_flat",
    "nest_96_wellplate_200ul_flat",
]
PIPETTES = ["p20_single_gen2", "p300_single_gen2", "p1000_single_gen2"]
MODULES = ["temperature module gen2", "heaterShakerModuleV1"]


def run_analyze(fixture: Path, check: bool) -> dict:
    """Invoke analyze via subprocess; return {exit_code, stdout_json, stderr_tail}.

    VERIFIED invocation (opentrons 8.8.2): `analyze` is a click SUBCOMMAND of the
    `opentrons.cli` group -- NOT `-m opentrons.cli.analyze` (that no-ops).
    """
    cmd = [sys.executable, "-m", "opentrons.cli", "analyze", "--json-output", "-"]
    if check:
        cmd.append("--check")
    cmd.append(str(fixture))
    p = subprocess.run(cmd, capture_output=True, text=True)
    stdout = p.stdout
    parsed = None
    if stdout and "{" in stdout:
        try:
            parsed = json.loads(stdout[stdout.index("{"):])
        except json.JSONDecodeError:
            parsed = None
    return {
        "exit_code": p.returncode,
        "parsed": parsed,
        "stderr_tail": "\n".join(p.stderr.strip().splitlines()[-6:]),
    }


def error_shape(parsed: dict | None) -> list[dict]:
    if not parsed:
        return []
    return [
        {
            "keys": sorted(e.keys()),
            "errorType": e.get("errorType"),
            "errorCode": e.get("errorCode"),
            "detail_head": (e.get("detail") or "")[:160],
            "has_wrappedErrors": bool(e.get("wrappedErrors")),
        }
        for e in parsed.get("errors", [])
    ]


def verify_library() -> dict:
    """Load each labware/pipette on virtual hardware; record what actually exists."""
    from opentrons.simulate import get_protocol_api

    ctx = get_protocol_api("2.20")  # OT-2 default
    lw_ok, lw_bad, slot = {}, {}, 1
    for name in LABWARE:
        try:
            ctx.load_labware(name, slot)
            lw_ok[name] = True
            slot += 1
        except Exception as e:  # noqa: BLE001
            lw_bad[name] = f"{type(e).__name__}: {e}"[:140]
    pip_ok, pip_bad = {}, {}
    for name in PIPETTES:
        try:
            # fresh context per pipette so mounts never collide
            get_protocol_api("2.20").load_instrument(name, "right")
            pip_ok[name] = True
        except Exception as e:  # noqa: BLE001
            pip_bad[name] = f"{type(e).__name__}: {e}"[:140]
    return {"labware_ok": lw_ok, "labware_bad": lw_bad, "pipettes_ok": pip_ok, "pipettes_bad": pip_bad}


def main() -> int:
    import opentrons
    from opentrons.protocols.api_support.definitions import MAX_SUPPORTED_VERSION

    contract: dict = {
        "opentrons_version": opentrons.__version__,
        "python_version": sys.version.split()[0],
        "max_supported_apiLevel": str(MAX_SUPPORTED_VERSION),
        "analyze_invocation": "python -m opentrons.cli analyze --json-output - [--check] [--rtp-values '{...}'] PROTOCOL.py [labware.json ...]",
        "fixtures": {},
    }

    for fx in ["good_minimal", "good_dilution", "bad_overaspirate"]:
        path = FIX / f"{fx}.py"
        no_check = run_analyze(path, check=False)
        with_check = run_analyze(path, check=True)
        parsed = with_check["parsed"] or no_check["parsed"]
        if parsed is not None:
            (OUT / f"{fx}.analysis.json").write_text(json.dumps(parsed, indent=2))
        contract["fixtures"][fx] = {
            "result": (parsed or {}).get("result"),
            "n_commands": len((parsed or {}).get("commands", [])),
            "n_errors": len((parsed or {}).get("errors", [])),
            "top_level_keys": sorted((parsed or {}).keys()),
            "exit_code_no_check": no_check["exit_code"],
            "exit_code_with_check": with_check["exit_code"],
            "error_shape": error_shape(parsed),
            "stderr_tail": with_check["stderr_tail"],
        }

    contract["library"] = verify_library()

    (OUT / "analyze_contract.json").write_text(json.dumps(contract, indent=2))
    _write_md(contract)
    print(json.dumps({k: contract[k] for k in
                      ["opentrons_version", "python_version", "max_supported_apiLevel"]}, indent=2))
    for fx, d in contract["fixtures"].items():
        print(f"  {fx:18} result={d['result']!s:6} "
              f"exit(no/check)={d['exit_code_no_check']}/{d['exit_code_with_check']} "
              f"cmds={d['n_commands']} errs={d['n_errors']}")
    lib = contract["library"]
    print(f"  labware ok={list(lib['labware_ok'])}  bad={list(lib['labware_bad'])}")
    print(f"  pipettes ok={list(lib['pipettes_ok'])}  bad={list(lib['pipettes_bad'])}")
    print(f"\nWrote {OUT}/analyze_contract.{{json,md}} + golden *.analysis.json")
    return 0


def _write_md(c: dict) -> None:
    lines = [
        "# Captured `opentrons analyze` contract (M1)",
        "",
        f"- **opentrons**: `{c['opentrons_version']}`  ·  **python**: `{c['python_version']}`  "
        f"·  **MAX apiLevel**: `{c['max_supported_apiLevel']}`",
        f"- **invocation**: `{c['analyze_invocation']}`",
        "",
        "## Exit codes & result (observed)",
        "",
        "| fixture | result | exit (no --check) | exit (--check) | errors |",
        "|---|---|---|---|---|",
    ]
    for fx, d in c["fixtures"].items():
        lines.append(f"| {fx} | `{d['result']}` | {d['exit_code_no_check']} | "
                     f"{d['exit_code_with_check']} | {d['n_errors']} |")
    lines += ["", "## ErrorOccurrence shape (bad fixture)", ""]
    bad = c["fixtures"].get("bad_overaspirate", {})
    for e in bad.get("error_shape", []):
        lines.append(f"- keys=`{e['keys']}` type=`{e['errorType']}` code=`{e['errorCode']}` "
                     f"wrapped={e['has_wrappedErrors']}")
        lines.append(f"  - detail: {e['detail_head']}")
    lib = c["library"]
    lines += ["", "## Library verification", "",
              f"- labware OK: {list(lib['labware_ok'])}",
              f"- labware MISSING: {lib['labware_bad'] or '(none)'}",
              f"- pipettes OK: {list(lib['pipettes_ok'])}",
              f"- pipettes MISSING: {lib['pipettes_bad'] or '(none)'}"]
    (OUT / "analyze_contract.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
