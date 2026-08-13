"""Valid protocol, but the 25% well is silently under-dosed to 20% v/v.
Simulates CLEAN (result: ok) — only the commands[] ledger reveals the error."""
from opentrons import protocol_api

metadata = {"protocolName": "doctored dilution", "author": "p2p"}
requirements = {"robotType": "OT-2", "apiLevel": "2.20"}


def run(protocol: protocol_api.ProtocolContext):
    tips = protocol.load_labware("opentrons_96_tiprack_300ul", 1)
    res = protocol.load_labware("nest_12_reservoir_15ml", 2)
    plate = protocol.load_labware("corning_24_wellplate_3.4ml_flat", 3)
    p300 = protocol.load_instrument("p300_single_gen2", "right", tip_racks=[tips])
    stock, diluent = res["A1"], res["A2"]
    total = 200.0
    plan = {"A1": (0.0, 200.0), "A2": (30.0, 170.0), "A3": (40.0, 160.0)}  # A3 is 20%, not 25%
    for well, (v_stock, v_dil) in plan.items():
        if v_dil > 0:
            p300.transfer(v_dil, diluent, plate[well], new_tip="always")
        if v_stock > 0:
            p300.transfer(v_stock, stock, plate[well], new_tip="always")
