from opentrons import protocol_api
metadata = {"protocolName": "x", "apiLevel": "2.20"}
requirements = {"robotType": "OT-2", "apiLevel": "2.20"}
def run(protocol: protocol_api.ProtocolContext):
    protocol.load_labware("opentrons_96_tiprack_300ul", 1)
