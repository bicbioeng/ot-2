"""M6 — the deterministic validate->repair loop gate.

`loop.py` is the SOLE acceptance authority (the panel's rule): pure Python over
JSON facts from the real judges. No LLM — and not the orchestrating agent —
decides CONVERGED. The generator only proposes drafts; this gate accepts, rejects,
or blocks.

The generator is injected as a `DraftProvider`:
  - ScriptedProvider  -> a fixed list of drafts (offline demo; every DETECTION is
    still the real engine).
  - (later) an LLMProvider that regenerates from `Feedback`.

Order per iteration (fail-fast, cheap->expensive):
  static_checks  ->  opentrons analyze  ->  conformance
A stage failure short-circuits: the later stages aren't spent, feedback is built,
and the next draft is requested. Anti-oscillation: track each iteration's error
SIGNATURE set; if a signature set recurs (iter N == N-2) we flag stagnation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from .conformance import ConformanceReport, check_dilution
from .simulate import AnalyzeResult, analyze
from .static_checks import StaticFinding, check_source


@dataclass
class Feedback:
    """What the gate hands back to the generator to drive the next draft."""

    iteration: int
    static_failures: list[StaticFinding] = field(default_factory=list)
    analyze_errors: list = field(default_factory=list)      # ParsedError
    conformance_failures: list = field(default_factory=list)  # ConformanceCheck
    reflexion_memo: list[str] = field(default_factory=list)

    def as_text(self) -> str:
        lines = []
        for f in self.static_failures:
            lines.append(f"[static:{f.rule} L{f.line}] {f.message}")
        for e in self.analyze_errors:
            lines.append(f"[analyze] {e.hint()}")
        for c in self.conformance_failures:
            lines.append(f"[conformance:{c.name}] {c.detail}")
        return "\n".join(lines)


@dataclass
class Draft:
    source: str
    path: Path
    label: str = ""
    generator_note: str = ""


class DraftProvider(Protocol):
    def __call__(self, feedback: Feedback | None, iteration: int) -> Draft | None: ...


@dataclass
class IterationRecord:
    iteration: int
    label: str
    stage_reached: str                 # "static" | "analyze" | "conformance" | "converged"
    static_findings: list[StaticFinding]
    analyze_result: AnalyzeResult | None
    conformance: ConformanceReport | None
    passed: bool
    signatures: set[str] = field(default_factory=set)


@dataclass
class LoopOutcome:
    status: str                        # "converged" | "blocked"
    reason: str
    iterations: list[IterationRecord]
    final: Draft | None


def _signatures(static_f, analyze_r, conf_r) -> set[str]:
    s = {f.signature() for f in static_f if f.severity == "error"}
    if analyze_r is not None:
        s |= analyze_r.error_signatures()
    if conf_r is not None:
        s |= {c.signature() for c in conf_r.failures()}
    return s


def run_loop(
    provider: DraftProvider,
    ir: dict,
    *,
    rtp_values: dict | None = None,
    cap: int = 5,
    on_event: Callable[[str, dict], None] | None = None,
) -> LoopOutcome:
    """Drive the loop to CONVERGED or BLOCKED. Deterministic; no model in the gate."""
    def emit(kind: str, **data):
        if on_event:
            on_event(kind, data)

    records: list[IterationRecord] = []
    sig_history: list[set[str]] = []
    feedback: Feedback | None = None
    memo: list[str] = []

    for i in range(1, cap + 1):
        draft = provider(feedback, i)
        if draft is None:
            return LoopOutcome("blocked", "generator exhausted (no further drafts)", records, None)
        emit("draft", iteration=i, label=draft.label, note=draft.generator_note)

        # --- Stage 5a: static ---
        static = check_source(draft.source, ir)
        static_errs = [f for f in static if f.severity == "error"]
        emit("static", iteration=i, findings=[(f.rule, f.line, f.message) for f in static])
        if static_errs:
            sigs = _signatures(static_errs, None, None)
            records.append(IterationRecord(i, draft.label, "static", static, None, None, False, sigs))
            memo.append(f"iter{i}: static {[f.rule for f in static_errs]} — fix, do not repeat")
            feedback = Feedback(i, static_failures=static_errs, reflexion_memo=list(memo))
            sig_history.append(sigs)
            _check_stagnation(sig_history, emit)
            continue

        # --- Stage 5b: analyze (the real judge) ---
        ar = analyze(draft.path, rtp_values=rtp_values)
        emit("analyze", iteration=i, result=ar.result, n_errors=len(ar.errors),
             n_commands=ar.n_commands, errors=[e.hint() for e in ar.errors])
        if not ar.ok:
            sigs = _signatures([], ar, None)
            records.append(IterationRecord(i, draft.label, "analyze", static, ar, None, False, sigs))
            memo.append(f"iter{i}: analyze {[e.root_type for e in ar.errors]} — fix")
            feedback = Feedback(i, analyze_errors=ar.errors, reflexion_memo=list(memo))
            sig_history.append(sigs)
            _check_stagnation(sig_history, emit)
            continue

        # --- Stage 5c: conformance (from the commands[] ledger) ---
        conf = check_dilution(ar.raw, ir)
        emit("conformance", iteration=i, ok=conf.ok,
             checks=[(c.name, c.ok, c.detail) for c in conf.checks])
        if not conf.ok:
            sigs = _signatures([], None, conf)
            records.append(IterationRecord(i, draft.label, "conformance", static, ar, conf, False, sigs))
            memo.append(f"iter{i}: conformance {[c.name for c in conf.failures()]} — fix volumes")
            feedback = Feedback(i, conformance_failures=conf.failures(), reflexion_memo=list(memo))
            sig_history.append(sigs)
            _check_stagnation(sig_history, emit)
            continue

        # --- all gates pass ---
        records.append(IterationRecord(i, draft.label, "converged", static, ar, conf, True, set()))
        emit("converged", iteration=i, label=draft.label)
        return LoopOutcome("converged", f"all gates passed at iteration {i}", records, draft)

    return LoopOutcome("blocked", f"hit iteration cap ({cap}) without converging", records, None)


def _check_stagnation(sig_history: list[set[str]], emit) -> None:
    """Signature recurrence (iter N == N-2) => oscillation; the panel's anti-thrash rule."""
    if len(sig_history) >= 3 and sig_history[-1] and sig_history[-1] == sig_history[-3]:
        emit("stagnation", signatures=sorted(sig_history[-1]))


class ScriptedProvider:
    """Offline generator: yields a fixed list of draft protocol files in order.

    The DETECTION at each step is still the real engine; only the 'who wrote the
    next draft' is scripted. Swap for an LLMProvider (regenerating from feedback)
    once a generator key is configured.
    """

    def __init__(self, paths: list[str | Path], labels: list[str] | None = None,
                 notes: list[str] | None = None):
        self.paths = [Path(p) for p in paths]
        self.labels = labels or [p.stem for p in self.paths]
        self.notes = notes or [""] * len(self.paths)

    def __call__(self, feedback: Feedback | None, iteration: int) -> Draft | None:
        idx = iteration - 1
        if idx >= len(self.paths):
            return None
        p = self.paths[idx]
        return Draft(source=p.read_text(), path=p, label=self.labels[idx],
                     generator_note=self.notes[idx])
