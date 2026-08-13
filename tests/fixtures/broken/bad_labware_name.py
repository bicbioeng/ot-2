from opentrons import protocol_api
requirements = {"robotType": "OT-2", "apiLevel": "2.20"}
def run(protocol: protocol_api.ProtocolContext):
    protocol.load_labware("corning_99_bogus_plate", 1)
