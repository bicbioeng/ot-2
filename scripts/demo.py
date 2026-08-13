"""Paper2Protocol — end-to-end demo on the E. coli chemotaxis / PenStrep paper.

Every DETECTION is the real engine (static_checks + opentrons analyze +
conformance). The generator is scripted offline (a buggy first draft -> fixes),
so this runs with NO API key. Swap ScriptedProvider for an LLMProvider to make
the generation live.

    uv run python scripts/demo.py            # narrated console demo
    uv run python scripts/demo.py --json     # also write examples/.../out/run.json

Outputs examples/chemotaxis_penstrep/out/run.json (fuel for the shareable page).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

from paper2protocol.conformance import realized_final_concentration
from paper2protocol.loop import LoopOutcome, ScriptedProvider, run_loop

ROOT = Path(__file__).resolve().parent.parent
EX = ROOT / "examples" / "chemotaxis_penstrep"
OUT = EX / "out"
IR = json.loads((EX / "ir.json").read_text())
C = Console()

DRAFTS = [EX / "iterations" / f"draft{i}.py" for i in (1, 2, 3, 4)]
LABELS = [
    "draft 1",
    "draft 2",
    "draft 3",
    "draft 4",
]
NOTES = [
    "generator's first attempt",
    "regenerated after STATIC feedback (apiLevel + tip policy)",
    "regenerated after ANALYZE feedback (invalid well reference)",
    "regenerated after CONFORMANCE feedback (25% dose)",
]
STAGE_LABEL = {"static": "STATIC checks", "analyze": "opentrons analyze",
               "conformance": "CONFORMANCE (commands[] ledger)", "converged": "CONVERGED"}


def header() -> None:
    p = IR["paper"]
    C.print(Panel.fit(
        f"[bold]Paper2Protocol[/bold] — paper → validated Opentrons protocol\n"
        f"[dim]{p['title']}[/dim]",
        border_style="cyan"))
    part = IR["automation_partition"]
    t = Table(title="Honest automation partition (what the robot does vs. what it hands off)",
              show_lines=False, header_style="bold")
    t.add_column("ROBOT (OT-2)", style="green")
    t.add_column("HUMAN GATE", style="yellow")
    t.add_column("OFF-DECK / other instrument", style="dim")
    rows = max(len(part["ROBOT"]), len(part["GATE"]), len(part["OFF_DECK"]))
    for i in range(rows):
        t.add_row(
            "• " + part["ROBOT"][i] if i < len(part["ROBOT"]) else "",
            "• " + part["GATE"][i] if i < len(part["GATE"]) else "",
            "• " + part["OFF_DECK"][i] if i < len(part["OFF_DECK"]) else "",
        )
    C.print(t)
    if IR.get("open_clarifications"):
        C.print(Panel("\n".join("• " + c for c in IR["open_clarifications"]),
                      title="[yellow]Blocking clarifications surfaced (not silently guessed)",
                      border_style="yellow"))
    C.print()


def narrate(kind: str, data: dict) -> None:
    i = data.get("iteration")
    if kind == "draft":
        C.print(Rule(f"[bold]Iteration {i}[/bold] — {data['note']}", style="cyan"))
    elif kind == "static":
        errs = [f for f in data["findings"] if True]
        bad = [f for f in data["findings"]]  # rule,line,msg tuples
        real_errs = [f for f in bad]
        if any(True for _ in []):
            pass
        # findings tuples are (rule, line, message); severity not passed, infer via loop record later
        if data["findings"]:
            for rule, line, msg in data["findings"]:
                C.print(f"  [red]✗ STATIC[/red] [{rule} L{line}] {msg}")
        else:
            C.print("  [green]✓ STATIC[/green] clean")
    elif kind == "analyze":
        if data["result"] == "ok":
            C.print(f"  [green]✓ opentrons analyze[/green] result=ok, "
                    f"{data['n_commands']} commands, 0 errors  [dim](real engine)[/dim]")
        else:
            C.print(f"  [red]✗ opentrons analyze[/red] result={data['result']}")
            for e in data["errors"]:
                C.print(f"      [red]{e}[/red]")
    elif kind == "conformance":
        if data["ok"]:
            C.print("  [green]✓ CONFORMANCE[/green] realized dilution matches IR "
                    "[dim](reconstructed from commands[] ledger)[/dim]")
        else:
            C.print("  [red]✗ CONFORMANCE[/red] realized dilution ≠ IR:")
        for name, ok, detail in data["checks"]:
            mark = "[green]✓[/green]" if ok else "[red]✗[/red]"
            C.print(f"      {mark} {detail}")
    elif kind == "stagnation":
        C.print(f"  [yellow]⚠ stagnation[/yellow] repeated signature: {data['signatures']}")
    elif kind == "converged":
        C.print()


def summarize(outcome: LoopOutcome) -> None:
    C.print()
    if outcome.status == "converged":
        C.print(Panel.fit("[bold green]CONVERGED[/bold green]  "
                          f"{outcome.reason}", border_style="green"))
        stock = IR["dilution"]["stock_source"]["stock_conc"]
        t = Table(title="Realized final concentrations (from the commands[] ledger)",
                  header_style="bold")
        t.add_column("well"); t.add_column("v/v"); t.add_column("penicillin"); t.add_column("streptomycin")
        for tg in IR["dilution"]["targets"]:
            conc = realized_final_concentration(tg["vv"], stock)
            t.add_row(tg["well"], f"{tg['vv']*100:.0f}%",
                      f"{conc['penicillin_U_per_mL']:.0f} U/mL",
                      f"{conc['streptomycin_ug_per_mL']:.0f} µg/mL")
        C.print(t)
        C.print(Panel(
            "Status: [green]ready for human wet-lab sign-off[/green]  ·  "
            "[dim]validated = static + analyze + conformance pass; NOT 'safe to run' "
            "(agar casting/imaging are external; calibration/liquid-physics are off-model)[/dim]",
            border_style="dim"))
    else:
        C.print(Panel.fit(f"[bold red]BLOCKED[/bold red]  {outcome.reason}", border_style="red"))


def build_trace(outcome: LoopOutcome) -> dict:
    iters = []
    for rec in outcome.iterations:
        idx = rec.iteration - 1
        iters.append({
            "n": rec.iteration,
            "label": LABELS[idx] if idx < len(LABELS) else rec.label,
            "note": NOTES[idx] if idx < len(NOTES) else "",
            "stage_reached": rec.stage_reached,
            "stage_label": STAGE_LABEL.get(rec.stage_reached, rec.stage_reached),
            "passed": rec.passed,
            "static": [{"rule": f.rule, "line": f.line, "message": f.message,
                        "severity": f.severity} for f in rec.static_findings],
            "analyze": None if rec.analyze_result is None else {
                "result": rec.analyze_result.result,
                "n_commands": rec.analyze_result.n_commands,
                "errors": [{"root_type": e.root_type, "line": e.line, "code": e.error_code,
                            "detail": e.detail} for e in rec.analyze_result.errors],
            },
            "conformance": None if rec.conformance is None else {
                "ok": rec.conformance.ok,
                "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail,
                            "expected": c.expected, "found": c.found}
                           for c in rec.conformance.checks],
            },
        })
    stock = IR["dilution"]["stock_source"]["stock_conc"]
    realized = [{"well": tg["well"], "vv": tg["vv"],
                 "conc": realized_final_concentration(tg["vv"], stock)}
                for tg in IR["dilution"]["targets"]]
    return {
        "paper": IR["paper"],
        "partition": IR["automation_partition"],
        "clarifications": IR.get("open_clarifications", []),
        "status": outcome.status,
        "reason": outcome.reason,
        "iterations": iters,
        "realized_concentrations": realized,
        "engine": _engine_info(),
    }


def _engine_info() -> dict:
    contract = json.loads((ROOT / "captured" / "analyze_contract.json").read_text())
    return {
        "opentrons_version": contract["opentrons_version"],
        "python_version": contract["python_version"],
        "max_apiLevel": contract["max_supported_apiLevel"],
        "invocation": contract["analyze_invocation"],
    }


def main() -> int:
    header()
    outcome = run_loop(ScriptedProvider(DRAFTS, LABELS, NOTES), IR, on_event=narrate)
    summarize(outcome)
    if "--json" in sys.argv:
        OUT.mkdir(exist_ok=True)
        (OUT / "run.json").write_text(json.dumps(build_trace(outcome), indent=2))
        C.print(f"\n[dim]wrote {OUT / 'run.json'}[/dim]")
    return 0 if outcome.status == "converged" else 1


if __name__ == "__main__":
    raise SystemExit(main())
