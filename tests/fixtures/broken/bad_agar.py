from opentrons import protocol_api
requirements = {"robotType": "OT-2", "apiLevel": "2.20"}
def run(protocol: protocol_api.ProtocolContext):
    tips = protocol.load_labware("opentrons_96_tiprack_1000ul", 1)
    res = protocol.load_labware("nest_12_reservoir_15ml", 2)
    plate = protocol.load_labware("corning_24_wellplate_3.4ml_flat", 3)
    p1000 = protocol.load_instrument("p1000_single_gen2", "left", tip_racks=[tips])
    agar_source = res["A1"]
    p1000.transfer(200, agar_source, plate["A1"], new_tip="always")
