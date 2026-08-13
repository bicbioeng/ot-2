from opentrons import instruments, labware
metadata = {"apiLevel": "2.20"}
def run(protocol):
    plate = labware.load("corning_24_wellplate_3.4ml_flat", 2)
