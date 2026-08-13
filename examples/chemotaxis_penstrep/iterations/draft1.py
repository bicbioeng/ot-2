from opentrons import protocol_api
metadata = {"protocolName": "PenStrep dilution 0/15/25%", "apiLevel": "2.20"}
requirements = {"robotType": "OT-2", "apiLevel": "2.20"}
def run(protocol: protocol_api.ProtocolContext):
    tips = protocol.load_labware("opentrons_96_tiprack_300ul", 1)
    res = protocol.load_labware("nest_12_reservoir_15ml", 2)
    plate = protocol.load_labware("corning_24_wellplate_3.4ml_flat", 3)
    p300 = protocol.load_instrument("p300_single_gen2", "right", tip_racks=[tips])
    stock, diluent = res["A1"], res["A2"]
    plan = {"A1": (0.0, 200.0), "A2": (30.0, 170.0), "A3": (50.0, 150.0)}
    for well, (v_stock, v_dil) in plan.items():
        if v_dil > 0:
            p300.transfer(v_dil, diluent, plate[well])
        if v_stock > 0:
            p300.transfer(v_stock, stock, plate[well])
