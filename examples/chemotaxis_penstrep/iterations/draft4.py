"""M1 golden GOOD (realistic): the aqueous PenStrep dilution series.

This doubles as the reference protocol for the conformance checker (M3): a
0 / 15 / 25 % v/v PenStrep series into 200 uL total, one destination well each,
new_tip='always' (carryover guard), liquids declared (overflow tracking).

Uses ONLY the aqueous robot job (locked scope). No agar, no plate casting.
"""
from opentrons import protocol_api

metadata = {"protocolName": "PenStrep dilution series 0/15/25%", "author": "paper2protocol"}
requirements = {"robotType": "OT-2", "apiLevel": "2.20"}


def run(protocol: protocol_api.ProtocolContext):
    tips300 = protocol.load_labware("opentrons_96_tiprack_300ul", 1)
    reservoir = protocol.load_labware("nest_12_reservoir_15ml", 2)
    plate = protocol.load_labware("corning_24_wellplate_3.4ml_flat", 3)
    p300 = protocol.load_instrument("p300_single_gen2", "right", tip_racks=[tips300])

    stock = reservoir["A1"]     # PenStrep 100x stock (10,000 U/mL penicillin)
    diluent = reservoir["A2"]   # LB broth

    # Declare liquids so the engine can track volumes (overflow bookkeeping).
    penstrep = protocol.define_liquid(
        name="PenStrep stock", description="10000 U/mL pen + 10000 ug/mL strep", display_color="#d43d3d"
    )
    lb = protocol.define_liquid(name="LB diluent", description="LB broth", display_color="#3d9d43")
    stock.load_liquid(penstrep, volume=5000)
    diluent.load_liquid(lb, volume=12000)

    # target v/v fraction -> destination well
    targets = {"A1": 0.0, "A2": 0.15, "A3": 0.25}
    total_ul = 200.0
    for well, frac in targets.items():
        v_stock = round(total_ul * frac, 1)
        v_dil = round(total_ul - v_stock, 1)
        dest = plate[well]
        if v_dil > 0:
            p300.transfer(v_dil, diluent, dest, new_tip="always")
        if v_stock > 0:
            p300.transfer(v_stock, stock, dest, new_tip="always", mix_after=(3, 100))
