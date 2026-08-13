"""Export: the converged run writes a bundle whose protocol.py re-validates clean."""
import json
from pathlib import Path

from paper2protocol.artifact import write_bundle
from paper2protocol.loop import ScriptedProvider, run_loop
from paper2protocol.simulate import analyze

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples" / "chemotaxis_penstrep"
IR = json.loads((EX / "ir.json").read_text())
DRAFTS = [EX / "iterations" / f"draft{i}.py" for i in (1, 2, 3, 4)]


def test_export_bundle_and_revalidate(tmp_path):
    outcome = run_loop(ScriptedProvider(DRAFTS), IR)
    assert outcome.status == "converged"
    manifest = write_bundle(tmp_path / "bundle", IR, outcome, project_root=ROOT)
    b = tmp_path / "bundle"
    for f in ("protocol.py", "ir.json", "analysis.json", "conformance.json",
              "run_log.json", "signoff.md", "MANIFEST.json"):
        assert (b / f).exists(), f"missing {f}"
    # the exported protocol still passes the real engine
    assert analyze(b / "protocol.py").ok
    # realized final concentration carried into the manifest
    a3 = manifest["realized_concentrations"][2]["final_concentration"]
    assert a3["penicillin_U_per_mL"] == 2500.0
    assert "wet-lab sign-off" in (b / "signoff.md").read_text().lower()
