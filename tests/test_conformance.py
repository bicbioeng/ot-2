"""M3 acceptance: conformance reconstructs realized dilution from commands[] and
catches BOTH a doctored-volume protocol and a right-literals/wrong-volume one —
even though both simulate clean.
"""
from pathlib import Path

import pytest

from paper2protocol.conformance import (
    check_dilution,
    dest_ledger,
    realized_final_concentration,
)
from paper2protocol.simulate import analyze

FIX = Path(__file__).parent / "fixtures"
BROKEN = FIX / "broken"

IR = {
    "dilution": {
        "stock_source": {
            "labware": "nest_12_reservoir_15ml",
            "well": "A1",
            "stock_conc": {"penicillin_U_per_mL": 10000, "streptomycin_ug_per_mL": 10000},
        },
        "diluent_source": {"labware": "nest_12_reservoir_15ml", "well": "A2"},
        "dest_labware": "corning_24_wellplate_3.4ml_flat",
        "targets": [{"well": "A1", "vv": 0.0}, {"well": "A2", "vv": 0.15}, {"well": "A3", "vv": 0.25}],
        "tolerance_vv": 0.01,
    }
}


def _raw(fixture_path):
    return analyze(fixture_path).raw


def test_good_dilution_conforms():
    rep = check_dilution(_raw(FIX / "good_dilution.py"), IR)
    assert rep.ok, [c.detail for c in rep.failures()]


def test_doctored_volume_caught():
    rep = check_dilution(_raw(BROKEN / "doctored_dilution.py"), IR)
    assert not rep.ok
    failed = {c.name for c in rep.failures()}
    assert "dilution[A3]" in failed  # 20% delivered where 25% expected
    a3 = next(c for c in rep.checks if c.name == "dilution[A3]")
    assert abs(a3.found - 0.20) < 1e-6


def test_reward_hack_caught_despite_right_literals():
    """The literals [0,15,25] are in the source; the ledger delivers 10% everywhere."""
    rep = check_dilution(_raw(BROKEN / "reward_hack_dilution.py"), IR)
    assert not rep.ok
    # A2 (want .15) and A3 (want .25) both realized 0.10 -> fail
    for well in ("A2", "A3"):
        c = next(c for c in rep.checks if c.name == f"dilution[{well}]")
        assert not c.ok and abs(c.found - 0.10) < 1e-6


def test_ledger_reconstruction():
    raw = _raw(FIX / "good_dilution.py")
    led = dest_ledger(raw["commands"], raw["labware"], "corning_24_wellplate_3.4ml_flat")
    # A3 = 50uL stock + 150uL diluent
    a3 = led["A3"]
    stock = a3[("nest_12_reservoir_15ml", "A1")]
    diluent = a3[("nest_12_reservoir_15ml", "A2")]
    assert (stock, diluent) == (50.0, 150.0)


def test_realized_final_concentration_units():
    conc = realized_final_concentration(0.15, IR["dilution"]["stock_source"]["stock_conc"])
    assert conc == {"penicillin_U_per_mL": 1500.0, "streptomycin_ug_per_mL": 1500.0}
