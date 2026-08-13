"""paper2protocol — command-line entrypoint.

    paper2protocol run                      # scripted demo loop (no key)
    paper2protocol run --live               # live generator model (needs a key)
    paper2protocol run --live --provider openai --model gpt-4.1
    paper2protocol run --export out/bundle  # write the artifact bundle (protocol.py, ...)
    paper2protocol run --live --export out/bundle --json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

from .artifact import write_bundle
from .conformance import realized_final_concentration
from .dispatch import OT2Client, VirtualOT2, dispatch_to_virtual
from .loop import ScriptedProvider, run_loop

ROOT = Path(__file__).resolve().parents[2]
EX = ROOT / "examples" / "chemotaxis_penstrep"
C = Console()

_SCRIPTED = [EX / "iterations" / f"draft{i}.py" for i in (1, 2, 3, 4)]
_NOTES = [
    "generator's first attempt",
    "regenerated after static feedback",
    "regenerated after analyze feedback",
    "regenerated after conformance feedback",
]


def _header(ir: dict) -> None:
    p = ir.get("paper", {})
    C.print(Panel.fit(f"[bold]Paper2Protocol[/bold] — paper → validated Opentrons protocol\n"
                      f"[dim]{p.get('title', '')}[/dim]", border_style="cyan"))


def _narrator():
    def on(kind: str, data: dict) -> None:
        i = data.get("iteration")
        if kind == "draft":
            C.print(Rule(f"[bold]Iteration {i}[/bold] — {data['note']}", style="cyan"))
        elif kind == "static":
            if data["findings"]:
                for rule, line, msg in data["findings"]:
                    C.print(f"  [red]✗ static[/red] [{rule} L{line}] {msg}")
            else:
                C.print("  [green]✓ static[/green] clean")
        elif kind == "analyze":
            if data["result"] == "ok":
                C.print(f"  [green]✓ analyze[/green] result=ok, {data['n_commands']} commands, 0 errors")
            else:
                C.print(f"  [red]✗ analyze[/red] result={data['result']}")
                for e in data["errors"]:
                    C.print(f"      [red]{e[:160]}[/red]")
        elif kind == "conformance":
            C.print(("  [green]✓ conformance[/green] realized dilution matches spec"
                     if data["ok"] else "  [red]✗ conformance[/red]:"))
            for name, ok, detail in data["checks"]:
                C.print(f"      {'[green]✓[/green]' if ok else '[red]✗[/red]'} {detail}")
        elif kind == "stagnation":
            C.print(f"  [yellow]⚠ stagnation[/yellow] {data['signatures']}")
    return on


def _summarize(outcome, ir: dict) -> None:
    C.print()
    if outcome.status == "converged":
        C.print(Panel.fit(f"[bold green]CONVERGED[/bold green]  {outcome.reason}", border_style="green"))
        stock = ir["dilution"]["stock_source"].get("stock_conc") or {}
        units = list(stock.keys())
        if units:
            t = Table(title="Realized final concentrations", header_style="bold")
            t.add_column("well"); t.add_column("v/v")
            for u in units:
                t.add_column(u)
            for tg in ir["dilution"]["targets"]:
                c = realized_final_concentration(tg["vv"], stock)
                t.add_row(tg["well"], f"{tg['vv']*100:.0f}%", *[f"{c[u]:g}" for u in units])
            C.print(t)
    else:
        C.print(Panel.fit(f"[bold red]BLOCKED[/bold red]  {outcome.reason}", border_style="red"))


def _dispatch_narrator():
    def on(kind: str, d: dict) -> None:
        if kind == "health":
            C.print(f"  [cyan]robot[/cyan] {d.get('name')} · {d.get('model')} · API {d.get('api')}")
        elif kind == "uploaded":
            a = d.get("analysis", {})
            C.print(f"  [green]uploaded[/green] {d['protocol_id']} · analysis "
                    f"result={a.get('result')} commands={a.get('commandCount')}")
        elif kind == "run_created":
            C.print(f"  [green]run created[/green] {d['run_id']}")
        elif kind == "play":
            C.print(f"  [green]play[/green] → robot executing")
        elif kind == "status":
            colour = {"succeeded": "green", "failed": "red", "running": "yellow"}.get(d["status"], "white")
            C.print(f"    status: [{colour}]{d['status']}[/{colour}]")
    return on


def _do_dispatch(protocol_path, robot_url: str | None) -> dict:
    C.print(Rule("[bold]Stage 06 — dispatch to the OT-2[/bold]", style="cyan"))
    C.print("[dim]In production this is gated on the wet-lab sign-off sheet. "
            "Here the target is a simulated OT-2 (same Runs API — point --robot-url at a real one).[/dim]")
    nar = _dispatch_narrator()
    if robot_url:
        client = OT2Client(robot_url)
        try:
            result = client.run_to_completion(protocol_path, on_event=nar)
        finally:
            client.close()
    else:
        result = dispatch_to_virtual(protocol_path, on_event=nar)
    ok = result["status"] == "succeeded"
    C.print(Panel.fit(
        f"[bold {'green' if ok else 'red'}]RUN {result['status'].upper()}[/bold {'green' if ok else 'red'}]"
        f"  run {result['run_id']} on {result.get('robot_url', robot_url)}",
        border_style="green" if ok else "red"))
    return result


def _print_ir_summary(ir: dict) -> None:
    p = ir.get("paper", {})
    C.print(Panel.fit(f"[bold]extracted spec[/bold]  [dim]{(p.get('title') or '')[:74]}[/dim]",
                      border_style="cyan"))
    dil = ir.get("dilution")
    if dil:
        tgts = ", ".join(f"{t['well']}={t['vv']*100:.0f}%" for t in dil.get("targets", []))
        stock = dil.get("stock_source", {})
        C.print(f"  [green]dilution[/green]: {tgts}  in {dil.get('dest_labware')} · "
                f"{dil.get('total_vol_ul')} uL total")
        C.print(f"  [green]stock[/green]: {stock.get('liquid')} {stock.get('stock_conc')} "
                f"@ {stock.get('labware')} {stock.get('well')}")
    for c in ir.get("open_clarifications", []):
        C.print(f"  [yellow]clarify[/yellow] {c}")
    C.print()


@click.group()
def main() -> None:
    """Paper -> validated Opentrons protocol, via a deterministically-gated repair loop."""


@main.command()
@click.argument("pdf", required=False)
@click.option("--live/--scripted", default=False, help="use a live generator model (needs an API key)")
@click.option("--provider", default=None, help="google | openai | anthropic (default: env or google)")
@click.option("--model", default=None, help="override the model id (PAPER2PROTOCOL_MODEL)")
@click.option("--export", "export_dir", default=None, help="write the artifact bundle to DIR")
@click.option("--cap", default=5, show_default=True, help="max repair iterations")
@click.option("--as-json", "as_json", is_flag=True, help="print the run trace as JSON")
@click.option("--ir", "ir_path", default=None, help="path to an IR json (default: the chemotaxis demo)")
@click.option("--dispatch", is_flag=True, help="after CONVERGED, dispatch to an OT-2 (simulated by default)")
@click.option("--robot-url", default=None, help="real OT-2 base URL for --dispatch (e.g. http://ROBOT_IP:31950)")
def run(pdf, live, provider, model, export_dir, cap, as_json, ir_path, dispatch, robot_url):
    """Run the generate -> validate -> repair loop to CONVERGED (or BLOCKED)."""
    from .providers.base import get_provider, load_env
    load_env(ROOT / ".env")
    prov = None
    if pdf or live:
        try:
            prov = get_provider(provider, model)
        except Exception as e:  # noqa: BLE001
            C.print(Panel.fit(f"[red]Cannot start generator:[/red] {e}\n"
                              f"[dim]Add a key to {ROOT/'.env'} (see .env.example).[/dim]",
                              border_style="red"))
            raise SystemExit(2)

    if pdf:
        from .extract import ingest as ingest_pdf
        C.print(f"[cyan]ingesting[/cyan] {pdf}  [dim]-> methods -> spec, via {prov.name}:{prov.model}[/dim]")
        try:
            ir = ingest_pdf(pdf, prov)
        except Exception as e:  # noqa: BLE001
            C.print(Panel.fit(f"[red]Extraction failed:[/red] {e}", border_style="red"))
            raise SystemExit(2)
        _print_ir_summary(ir)
        if not ir.get("dilution"):
            C.print(Panel.fit("[yellow]No automatable aqueous dilution/concentration series found in "
                              "this paper.[/yellow] The robot only does aqueous liquid handling; see the "
                              "clarifications above.", border_style="yellow"))
            raise SystemExit(3)
        live = True  # generation from a freshly-extracted spec is always live
    elif ir_path:
        ir = json.loads(Path(ir_path).read_text())
    else:
        ir = json.loads((EX / "ir.json").read_text())

    _header(ir)

    if live:
        from .codegen import LLMDraftProvider
        C.print(f"[cyan]live generator[/cyan]: {prov.name} · [bold]{prov.model}[/bold]  "
                f"[dim](validator = this deterministic engine)[/dim]\n")
        dprovider = LLMDraftProvider(prov, ir, EX / "out" / "live_drafts")
    else:
        C.print("[dim]scripted generator (offline demo — every detection is the real engine)[/dim]\n")
        dprovider = ScriptedProvider(_SCRIPTED, notes=_NOTES)

    try:
        outcome = run_loop(dprovider, ir, cap=cap, on_event=_narrator())
    except Exception as e:  # noqa: BLE001  (generation / API errors -> clean message)
        msg = str(e)
        hint = ""
        if "NOT_FOUND" in msg or "not available" in msg or "model" in msg.lower():
            hint = "\n[dim]The model id may be wrong/retired. Override with --model, "
            hint += "or list valid ones for your key.[/dim]"
        C.print(Panel.fit(f"[red]Live generation failed:[/red] {msg[:400]}{hint}", border_style="red"))
        raise SystemExit(2)
    _summarize(outcome, ir)

    if export_dir:
        manifest = write_bundle(export_dir, ir, outcome, project_root=ROOT)
        C.print(f"\n[green]exported[/green] {len(manifest['files'])} files → [bold]{export_dir}[/bold]")
        for name, desc in manifest["files"].items():
            C.print(f"  • [bold]{name}[/bold] — [dim]{desc}[/dim]")

    if dispatch and outcome.status == "converged" and outcome.final is not None:
        C.print()
        _do_dispatch(outcome.final.path, robot_url)

    if as_json:
        print(json.dumps({"status": outcome.status, "reason": outcome.reason,
                          "iterations": len(outcome.iterations)}, indent=2))
    raise SystemExit(0 if outcome.status == "converged" else 1)


@main.command()
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8000, show_default=True)
def serve(host, port):
    """Launch the local web GUI (upload a PDF, watch the pipeline run)."""
    import uvicorn
    C.print(f"[cyan]Paper2Protocol GUI[/cyan]  ->  [bold]http://{host}:{port}[/bold]  "
            f"[dim](Ctrl-C to stop)[/dim]")
    uvicorn.run("paper2protocol.webapp:app", host=host, port=port, log_level="warning")


@main.command()
@click.argument("pdf", type=click.Path(exists=True))
@click.option("--out", "out_path", default=None, help="where to write the extracted IR (default: out/extracted_ir.json)")
@click.option("--provider", default=None, help="google | openai | anthropic")
@click.option("--model", default=None, help="override the model id")
def ingest(pdf, out_path, provider, model):
    """Ingest a paper (PDF) and extract the spec (IR). Needs a generator key."""
    from .extract import ingest as ingest_pdf
    from .providers.base import get_provider, load_env
    load_env(ROOT / ".env")
    try:
        prov = get_provider(provider, model)
    except Exception as e:  # noqa: BLE001
        C.print(Panel.fit(f"[red]{e}[/red]", border_style="red"))
        raise SystemExit(2)
    C.print(f"[cyan]ingesting[/cyan] {pdf}  [dim]via {prov.name}:{prov.model}[/dim]")
    ir = ingest_pdf(pdf, prov)
    _print_ir_summary(ir)
    out = Path(out_path) if out_path else EX / "out" / "extracted_ir.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(ir, indent=2))
    C.print(f"[green]wrote[/green] {out}")
    raise SystemExit(0 if ir.get("dilution") else 3)


@main.command()
@click.argument("protocol", type=click.Path(exists=True))
@click.option("--robot-url", default=None, help="real OT-2 base URL (default: a simulated OT-2)")
def dispatch(protocol, robot_url):
    """Dispatch a validated protocol to an OT-2 over the Runs API (simulated by default)."""
    result = _do_dispatch(protocol, robot_url)
    raise SystemExit(0 if result["status"] == "succeeded" else 1)


if __name__ == "__main__":
    main()
