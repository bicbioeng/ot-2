"""M2 acceptance: each intentionally-broken protocol is caught with the right rule.

Pure-AST, no opentrons/LLM needed — fast.
"""
from pathlib import Path

import pytest

from paper2protocol.static_checks import check_file

FIX = Path(__file__).parent / "fixtures"
BROKEN = FIX / "broken"


def rules(path) -> set[str]:
    return {f.rule for f in check_file(path)}


@pytest.mark.parametrize(
    "fixture,expected_rule",
    [
        ("bad_apilevel_both.py", "apilevel_placement"),
        ("bad_v1_syntax.py", "api_v1_syntax"),
        ("bad_labware_name.py", "labware_loadname"),
        ("bad_submin_volume.py", "volume_bounds"),
        ("bad_new_tip.py", "new_tip_policy"),
        ("bad_agar.py", "no_agar_pipetting"),
    ],
)
def test_broken_caught(fixture, expected_rule):
    found = rules(BROKEN / fixture)
    assert expected_rule in found, f"{fixture}: expected {expected_rule}, got {found}"


def test_submin_reports_line_and_message():
    findings = check_file(BROKEN / "bad_submin_volume.py")
    vb = [f for f in findings if f.rule == "volume_bounds"]
    assert vb and vb[0].line == 7  # the transfer(5, ...) line
    assert "below" in vb[0].message and "min 20" in vb[0].message


def test_good_fixtures_clean():
    """The good protocols must produce zero static ERRORS."""
    for good in ["good_minimal.py", "good_dilution.py"]:
        errs = [f for f in check_file(FIX / good) if f.severity == "error"]
        assert errs == [], f"{good} should be clean, got {[(f.rule, f.line) for f in errs]}"
