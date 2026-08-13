"""M1 acceptance: the deterministic judge behaves as captured.

These run the REAL opentrons analyze engine (slow-ish, ~seconds each) — they are
the trusted signal the whole loop is built on, so we test them directly.
"""
from pathlib import Path

import pytest

from paper2protocol.simulate import analyze

FIX = Path(__file__).parent / "fixtures"


def test_good_minimal_ok():
    r = analyze(FIX / "good_minimal.py")
    assert r.result == "ok"
    assert r.ok
    assert r.errors == []
    assert r.exit_code == 0
    assert r.n_commands > 0


def test_good_dilution_ok():
    """Our realistic aqueous PenStrep dilution simulates clean."""
    r = analyze(FIX / "good_dilution.py")
    assert r.ok, r.errors
    assert r.n_commands >= 40  # 3 wells x (diluent + stock transfers) w/ tip changes


def test_bad_overaspirate_parsed():
    r = analyze(FIX / "bad_overaspirate.py")
    assert r.result == "not-ok"
    assert not r.ok
    assert r.exit_code != 0
    assert len(r.errors) == 1
    e = r.errors[0]
    # root cause is the specific volume error, not the generic wrapper
    assert e.root_type == "InvalidAspirateVolumeError"
    assert e.error_code == "4000"
    assert e.line == 18  # aspirate(400,...) line in the fixture
    assert "400" in e.detail
    # structured info the loop can use
    assert e.error_info.get("max_tip_volume") == 300
    # signature is stable and identifies the bug
    assert e.signature() == "InvalidAspirateVolumeError|4000|L18"


def test_error_signature_excludes_volatile_ids():
    r1 = analyze(FIX / "bad_overaspirate.py")
    r2 = analyze(FIX / "bad_overaspirate.py")
    assert r1.error_signatures() == r2.error_signatures()
