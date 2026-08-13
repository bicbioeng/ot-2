"""The right literals [0, 15, 25] are present in a comment AND a variable, but the
actual pipetting delivers 10% to every well. A literal-grep conformance check
would PASS this; a commands[]-ledger check must FAIL it."""
from opentrons import protocol_api

metadata = {"protocolName": "PenStrep 0/15/25% series", "author": "p2p"}
requirements = {"robotType": "OT-2", "apiLevel": "2.20"}

# Target concentrations: 0, 15, 25 percent PenStrep v/v
PCT = [0, 15, 25]  # noqa: F841  (present but never used for volumes)


def run(protocol: protocol_api.ProtocolContext):
    tips = protocol.load_labware("opentrons_96_tiprack_300ul", 1)
    res = protocol.load_labware("nest_12_reservoir_15ml", 2)
    plate = protocol.load_labware("corning_24_wellplate_3.4ml_flat", 3)
    p300 = protocol.load_instrument("p300_single_gen2", "right", tip_racks=[tips])
    stock, diluent = res["A1"], res["A2"]
    for well in ["A1", "A2", "A3"]:  # deliver 20/200 = 10% everywhere
        p300.transfer(180.0, diluent, plate[well], new_tip="always")
        p300.transfer(20.0, stock, plate[well], new_tip="always")
