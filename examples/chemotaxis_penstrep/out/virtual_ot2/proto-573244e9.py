"""M1 golden BAD: aspirate 400 uL through a 300 uL tip.

This is the panel's confirmed genuinely-analyze-caught error class
(pipette-max / tip-capacity overrun -> ValueError). Purpose: capture the real
`result: "not-ok"` + ErrorOccurrence shape (errorType, errorCode, detail w/ line).
"""
from opentrons import protocol_api

metadata = {"protocolName": "M1 bad overaspirate", "author": "paper2protocol"}
requirements = {"robotType": "OT-2", "apiLevel": "2.20"}


def run(protocol: protocol_api.ProtocolContext):
    tips = protocol.load_labware("opentrons_96_tiprack_300ul", 1)
    plate = protocol.load_labware("corning_24_wellplate_3.4ml_flat", 2)
    p300 = protocol.load_instrument("p300_single_gen2", "right", tip_racks=[tips])
    p300.pick_up_tip()
    p300.aspirate(400, plate["A1"])  # 400 > 300 uL tip capacity -> error
    p300.dispense(400, plate["A2"])
    p300.drop_tip()
