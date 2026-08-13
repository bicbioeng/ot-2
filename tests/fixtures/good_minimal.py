"""M1 golden GOOD (minimal): guaranteed-valid OT-2 protocol at apiLevel 2.20.

Purpose: give the contract-capture a definite `result: "ok"` so we can lock the
parser to the real ok-shaped AnalyzeResults JSON.
"""
from opentrons import protocol_api

metadata = {"protocolName": "M1 minimal good", "author": "paper2protocol"}
requirements = {"robotType": "OT-2", "apiLevel": "2.20"}


def run(protocol: protocol_api.ProtocolContext):
    tips = protocol.load_labware("opentrons_96_tiprack_300ul", 1)
    plate = protocol.load_labware("corning_24_wellplate_3.4ml_flat", 2)
    p300 = protocol.load_instrument("p300_single_gen2", "right", tip_racks=[tips])
    p300.transfer(100, plate["A1"], plate["A2"], new_tip="always")
