from opentrons import protocol_api
requirements = {"robotType": "OT-2", "apiLevel": "2.20"}
def run(protocol: protocol_api.ProtocolContext):
    tips = protocol.load_labware("opentrons_96_tiprack_300ul", 1)
    plate = protocol.load_labware("corning_24_wellplate_3.4ml_flat", 2)
    p300 = protocol.load_instrument("p300_single_gen2", "right", tip_racks=[tips])
    for w in ["A1", "A2", "A3"]:
        p300.transfer(100, plate["B1"], plate[w])
