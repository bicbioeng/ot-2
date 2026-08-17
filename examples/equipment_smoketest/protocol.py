requirements = {"robotType": "OT-2"}
from opentrons import protocol_api

metadata = {
    "protocolName": "Equipment smoke test — modules + 8-channel",
    "author": "paper2protocol",
    "description": (
        "Not science. Exercises every piece of hardware the twin claims to support, "
        "so a claim of support is backed by a run you can watch: temperature module, "
        "magnetic module, thermocycler (lid open/close), an 8-channel pipette taking "
        "whole tip-rack columns, and a single-channel on the other mount."
    ),
    "apiLevel": "2.12",
}

# What this must prove on screen:
#   * each module renders at its real footprint and height
#   * labware STANDS ON the module — a temperature module lifts its plate 80.09 mm,
#     a thermocycler 97.8 mm. If the offset were ignored the plate would sit on the
#     deck while the pipette reached 80 mm above it, missing every well silently.
#   * the magnet rises on engage() and drops on disengage()
#   * the thermocycler lid lifts on open_lid() and closes on close_lid()
#   * the 8-channel takes EIGHT tips per pick-up and fills EIGHT wells per dispense
#   * travel height clears the tallest module instead of the tallest deck labware


def run(protocol: protocol_api.ProtocolContext):
    temp = protocol.load_module("temperature module gen2", "3")
    mag = protocol.load_module("magnetic module gen2", "6")
    tc = protocol.load_module("thermocycler module")

    temp_plate = temp.load_labware("corning_96_wellplate_360ul_flat")
    mag_plate = mag.load_labware("corning_96_wellplate_360ul_flat")

    src = protocol.load_labware("opentrons_15_tuberack_falcon_15ml_conical", "1")
    tips300 = protocol.load_labware("opentrons_96_tiprack_300ul", "4")
    tips20 = protocol.load_labware("opentrons_96_tiprack_20ul", "5")

    multi = protocol.load_instrument("p300_multi_gen2", "left", tip_racks=[tips300])
    single = protocol.load_instrument("p20_single_gen2", "right", tip_racks=[tips20])

    # ---- thermocycler lid, so the open/close motion is visible ----
    tc.open_lid()

    # ---- temperature module: warm the block ----
    temp.set_temperature(37)

    # ---- 8-channel: whole columns at a time ----
    # One pick_up_tip takes eight tips; one dispense fills eight wells.
    for col in range(1, 5):
        multi.pick_up_tip()
        multi.aspirate(150, src["A1"].bottom(3))
        multi.dispense(150, temp_plate[f"A{col}"].bottom(1))
        multi.drop_tip()

    # ---- magnetic module: engage, hold, release ----
    for col in range(1, 3):
        multi.pick_up_tip()
        multi.aspirate(100, src["A2"].bottom(3))
        multi.dispense(100, mag_plate[f"A{col}"].bottom(1))
        multi.drop_tip()

    mag.engage(height_from_base=10)
    protocol.delay(seconds=20, msg="Beads pelleting against the engaged magnet")
    mag.disengage()

    # ---- single channel on the other mount, same run ----
    for well in ("A6", "B6", "C6"):
        single.pick_up_tip()
        single.aspirate(15, src["A3"].bottom(3))
        single.dispense(15, temp_plate[well].bottom(1))
        single.drop_tip()

    # ---- close the lid again ----
    tc.close_lid()
    protocol.comment("Equipment smoke test complete.")
