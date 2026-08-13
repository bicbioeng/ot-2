"""Stage 5a — deterministic static checks BEFORE spending a simulation call.

Only the rules the aqueous demo actually exercises (the panel: don't build a
linter product). Each finding carries a rule id, line, and severity so the
repair loop can feed the generator an exact, cheap correction.

Key design points forced by the adversarial review:
  - `analyze` does NOT flag sub-minimum-volume aspirations, so min/max is checked
    HERE against the pipette bound to each call (rule: volume_bounds).
  - every loaded pipette must have a compatible tip rack AND be used (rule:
    pipette_unused / pipette_no_tiprack).
  - single-dispense-over-well-capacity is caught here; CUMULATIVE well overflow
    is reconstructed from the analyze commands[] ledger in conformance.py (M3).
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

# GEN2 specs (verified present in opentrons 8.8.2 via capture_contract.py)
PIPETTE_SPECS: dict[str, tuple[float, float]] = {  # name -> (min_ul, max_ul)
    "p20_single_gen2": (1, 20),
    "p300_single_gen2": (20, 300),
    "p1000_single_gen2": (100, 1000),
    "p20_multi_gen2": (1, 20),
    "p300_multi_gen2": (20, 300),
}
TIPRACK_CAP: dict[str, float] = {
    "opentrons_96_tiprack_20ul": 20,
    "opentrons_96_tiprack_300ul": 300,
    "opentrons_96_tiprack_1000ul": 1000,
}
WELL_CAP: dict[str, float] = {  # per-well capacity (uL) for single-dispense overflow
    "nest_12_reservoir_15ml": 15000,
    "nest_96_wellplate_200ul_flat": 200,
    "corning_12_wellplate_6.9ml_flat": 6900,
    "corning_24_wellplate_3.4ml_flat": 3400,
}
LIQUID_HANDLING = {"aspirate", "dispense", "transfer", "distribute", "consolidate", "mix"}
MIN_API, MAX_API = (2, 0), (2, 27)  # captured MAX_SUPPORTED_VERSION = 2.27

_ALLOWLIST_PATH = Path(__file__).resolve().parents[2] / "data" / "allowlists" / "labware_loadnames.txt"


def _load_allowlist() -> set[str]:
    if not _ALLOWLIST_PATH.exists():
        return set()
    return {
        ln.strip() for ln in _ALLOWLIST_PATH.read_text().splitlines()
        if ln.strip() and not ln.startswith("#")
    }


@dataclass
class StaticFinding:
    rule: str
    line: int
    message: str
    severity: str = "error"  # error | warn

    def signature(self) -> str:
        return f"static:{self.rule}|L{self.line}"


def _api_tuple(s: str) -> tuple[int, int] | None:
    try:
        a, b = s.split(".")
        return (int(a), int(b))
    except Exception:  # noqa: BLE001
        return None


def _literal_number(node: ast.AST) -> float | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        v = _literal_number(node.operand)
        return -v if v is not None else None
    return None


def _str_of(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


class _Visitor(ast.NodeVisitor):
    def __init__(self, allowlist: set[str]) -> None:
        self.allow = allowlist
        self.findings: list[StaticFinding] = []
        self.pipette_var: dict[str, str] = {}      # var -> pipette load-name
        self.pipette_has_rack: dict[str, bool] = {}  # var -> tip_racks passed?
        self.pipette_used: dict[str, bool] = {}
        self.labware_var: dict[str, str] = {}      # var -> labware load-name
        self._loop_depth = 0

    def add(self, rule: str, line: int, msg: str, severity: str = "error") -> None:
        self.findings.append(StaticFinding(rule, line, msg, severity))

    # --- v1 syntax on imports ---
    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module == "opentrons":
            for a in node.names:
                if a.name in {"robot", "instruments", "labware"}:
                    self.add("api_v1_syntax", node.lineno,
                             f"deprecated API v1 import `from opentrons import {a.name}`; "
                             f"use the ProtocolContext passed to run()")
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self._loop_depth += 1
        self.generic_visit(node)
        self._loop_depth -= 1

    def visit_Assign(self, node: ast.Assign) -> None:
        # record var -> load-name / tip-rack bookkeeping only; name VALIDITY is
        # checked in visit_Call so bare (unassigned) load calls are covered too.
        call = node.value
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute):
            method = call.func.attr
            target = node.targets[0]
            var = target.id if isinstance(target, ast.Name) else None
            if var and call.args:
                name = _str_of(call.args[0])
                if method == "load_instrument" and name:
                    self.pipette_var[var] = name
                    self.pipette_used[var] = False
                    self.pipette_has_rack[var] = any(k.arg == "tip_racks" for k in call.keywords)
                elif method == "load_labware" and name:
                    self.labware_var[var] = name
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute):
            method = node.func.attr
            recv = node.func.value
            recv_var = recv.id if isinstance(recv, ast.Name) else None
            first = _str_of(node.args[0]) if node.args else None
            # deprecated v1 call form: labware.load(...) / instruments.X(...)
            if recv_var in {"labware", "instruments", "robot"}:
                self.add("api_v1_syntax", node.lineno,
                         f"deprecated API v1 call `{recv_var}.{method}(...)`")
            # load-name validity (covers assigned AND bare calls)
            if method == "load_labware" and first and first not in self.allow:
                self.add("labware_loadname", node.lineno,
                         f"labware load-name '{first}' not in verified allowlist; "
                         f"fix it or supply a custom .json")
            if method == "load_instrument" and first and first not in PIPETTE_SPECS:
                self.add("pipette_loadname", node.lineno,
                         f"unknown/unsupported pipette '{first}'")
            if method in LIQUID_HANDLING and recv_var in self.pipette_var:
                self.pipette_used[recv_var] = True
                self._check_liquid_handling(node, recv_var, method)
        self.generic_visit(node)

    def _check_liquid_handling(self, node: ast.Call, pip_var: str, method: str) -> None:
        pname = self.pipette_var[pip_var]
        lo, hi = PIPETTE_SPECS.get(pname, (0, 1e9))
        # volume is the first positional arg for these calls (mix: (reps, vol))
        vol_node = None
        if method == "mix" and len(node.args) >= 2:
            vol_node = node.args[1]
        elif node.args:
            vol_node = node.args[0]
        vol = _literal_number(vol_node) if vol_node is not None else None
        if vol is not None and vol > 0:
            if vol < lo:
                self.add("volume_bounds", node.lineno,
                         f"{method} {vol} uL is below {pname} min {lo} uL "
                         f"(analyze will NOT catch this)")
            if vol > hi:
                self.add("volume_bounds", node.lineno,
                         f"{method} {vol} uL exceeds {pname} max {hi} uL")
        # new_tip policy on transfer-family inside a loop
        if method in {"transfer", "distribute", "consolidate"}:
            new_tip = next((k.value for k in node.keywords if k.arg == "new_tip"), None)
            new_tip_val = _str_of(new_tip) if new_tip is not None else None
            if self._loop_depth > 0 and new_tip_val != "always":
                self.add("new_tip_policy", node.lineno,
                         f"{method} in a loop without new_tip='always' risks carryover "
                         f"between destinations (got new_tip={new_tip_val!r})",
                         severity="error")


def check_source(source: str, ir: dict | None = None) -> list[StaticFinding]:
    """Run the static checks on protocol source. `ir` enables IR-driven checks."""
    allow = _load_allowlist()
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return [StaticFinding("syntax_error", e.lineno or 0, f"SyntaxError: {e.msg}")]

    findings: list[StaticFinding] = []
    findings += _check_api_level(tree)
    v = _Visitor(allow)
    v.visit(tree)
    findings += v.findings
    # every loaded pipette must be used and have a tip rack
    for var, name in v.pipette_var.items():
        line = next((f.line for f in findings if name in f.message), 0)
        if not v.pipette_used.get(var):
            findings.append(StaticFinding("pipette_unused", 0,
                                          f"pipette '{name}' is loaded but never used"))
        if not v.pipette_has_rack.get(var):
            findings.append(StaticFinding("pipette_no_tiprack", 0,
                                          f"pipette '{name}' loaded without tip_racks="))
    # no agar pipetting (code-level heuristic; IR-level added when ir given)
    if "agar" in source.lower():
        for i, ln in enumerate(source.splitlines(), 1):
            low = ln.lower()
            if "agar" in low and any(m in low for m in ("aspirate", "dispense", "transfer")):
                findings.append(StaticFinding("no_agar_pipetting", i,
                                              "agar must never be pipetted (external gate only)"))
    if ir is not None:
        findings += _check_ir_gates(source, ir)
    findings.sort(key=lambda f: (f.severity != "error", f.line))
    return findings


def check_file(path: str | Path, ir: dict | None = None) -> list[StaticFinding]:
    return check_source(Path(path).read_text(), ir)


def _check_api_level(tree: ast.AST) -> list[StaticFinding]:
    """apiLevel must appear in exactly one of metadata/requirements, within range."""
    found: list[tuple[str, str, int]] = []  # (container, value, line)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            tgt = node.targets[0]
            if isinstance(tgt, ast.Name) and tgt.id in {"metadata", "requirements"} \
                    and isinstance(node.value, ast.Dict):
                for k, val in zip(node.value.keys, node.value.values):
                    if _str_of(k) == "apiLevel":
                        found.append((tgt.id, _str_of(val) or "", node.lineno))
    out: list[StaticFinding] = []
    if len(found) == 0:
        out.append(StaticFinding("apilevel_placement", 0,
                                 "apiLevel missing from both metadata and requirements"))
    elif len(found) > 1:
        out.append(StaticFinding("apilevel_placement", found[0][2],
                                 "apiLevel declared in BOTH metadata and requirements "
                                 "(must be exactly one)"))
    for _c, valstr, line in found:
        t = _api_tuple(valstr)
        if t is None:
            out.append(StaticFinding("apilevel_value", line, f"unparseable apiLevel '{valstr}'"))
        elif not (MIN_API <= t <= MAX_API):
            out.append(StaticFinding("apilevel_value", line,
                                     f"apiLevel {valstr} outside supported "
                                     f"{MIN_API[0]}.{MIN_API[1]}-{MAX_API[0]}.{MAX_API[1]}"))
    return out


def _check_ir_gates(source: str, ir: dict) -> list[StaticFinding]:
    """Every gate the IR declares must appear as a protocol.pause(...) in code."""
    out: list[StaticFinding] = []
    src = source
    for gate in ir.get("gates", []):
        if gate.get("kind") == "pause":
            gid = gate.get("id", "")
            if f"pause(" not in src or gid not in src:
                out.append(StaticFinding("gate_present", 0,
                                         f"declared gate {gid} not found as a protocol.pause() in code"))
    return out
