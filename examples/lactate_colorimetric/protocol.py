requirements = {"robotType": "OT-2"}
from opentrons import protocol_api

metadata = {
    "protocolName": "Colorimetric L-lactate assay — standard curve",
    "author": "paper2protocol",
    "description": (
        "Standard-curve leg of the colorimetric L-lactate assay, replicating "
        "Schmiedeknecht, Kaufmann, Bauer & Venegas Solis, PLOS ONE 17(7):e0271818 (2022), "
        "doi:10.1371/journal.pone.0271818. Six-point two-fold sodium L-lactate series "
        "(12 to 0.375 mmol/L) in RPMI, 50 uL standard + 50 uL reaction mix per well, "
        "1 h dark incubation, stopped with 50 uL 1 mol/L acetic acid. Triplicate."
    ),
    "apiLevel": "2.12",
}

# ---------------------------------------------------------------------------
# FROM THE PAPER (Materials and methods), quoted:
#   "L-Lactate standards with the concentrations of 12-0,375 mmol/L were prepared
#    from sodium L-lactate in RPMI medium."
#   "Reactions were incubated for 1 h at room temperature and in dark before they
#    were stopped by addition of 50 uL acetic acid (1 mol/L)."
#   "absorbance was recorded with a microplate reader at 490 nm - 650 nm (reference)"
#
# 12 -> 0.375 mmol/L halving is exactly 6 points (12 / 2^5 = 0.375).
#
# IMPLEMENTATION DECISIONS (NOT stated in the paper — flagged for sign-off):
#   * 50 uL of reaction mix per well, matching the 50 uL stop volume the paper does
#     give, so the well ends at 150 uL — within a 360 uL Corning well.
#   * 300 uL equal-volume steps for the series in 1.5 mL Eppendorf tubes; leaves
#     300 uL per standard after passing 300 uL on, enough for 3 x 50 uL.
#   * Triplicate layout in rows A-C; the paper reports replicates but not the map.
#   * Fresh tip on every liquid change to prevent carryover.
#
# STEPS THE ROBOT CANNOT DO (handoff gates, same treatment as the chemotaxis
# agar hold): the 1 h dark incubation is emitted as protocol.delay(); the plate
# reader step at 490/650 nm is off-deck and is NOT part of this protocol.
# ---------------------------------------------------------------------------

STANDARDS = [12.0, 6.0, 3.0, 1.5, 0.75, 0.375]   # mmol/L
SERIES_TUBES = ["A1", "A2", "A3", "A4", "A5", "A6"]
SERIES_VOL = 300.0        # uL per two-fold step (implementation choice)
SAMPLE_VOL = 50.0         # uL of standard per well  (paper gives the 50 uL stop)
REACTION_VOL = 50.0       # uL of reaction mix per well
STOP_VOL = 50.0           # uL of 1 mol/L acetic acid — quoted
N_REPLICATES = 3
ROWS = ["A", "B", "C"]


def run(protocol: protocol_api.ProtocolContext):
    # ---------------- labware ----------------
    plate = protocol.load_labware("corning_96_wellplate_360ul_flat", "1")
    # a 12-trough reservoir and a 24 x 1.5 mL Eppendorf rack — deliberately
    # different geometry from the Falcon/plate decks used so far
    res = protocol.load_labware("nest_12_reservoir_15ml", "2")
    rack = protocol.load_labware(
        "opentrons_24_tuberack_eppendorf_1.5ml_safelock_snapcap", "3")
    tips = protocol.load_labware("opentrons_96_tiprack_300ul", "7")
    p300 = protocol.load_instrument("p300_single_gen2", "left", tip_racks=[tips])

    rpmi = res["A1"]          # RPMI medium — the diluent
    reaction = res["A2"]       # premixed reaction mix
    acetic = res["A3"]         # 1 mol/L acetic acid — the stop

    # ---------------- 1. build the six-point standard series ----------------
    # RPMI into every tube below the top standard
    for t in SERIES_TUBES[1:]:
        p300.pick_up_tip()
        p300.transfer(SERIES_VOL, rpmi, rack[t].bottom(2), new_tip="never")
        p300.drop_tip()

    # carry the lactate down the series, mixing at each step
    for src, dst in zip(SERIES_TUBES, SERIES_TUBES[1:]):
        p300.pick_up_tip()
        p300.transfer(SERIES_VOL, rack[src].bottom(2), rack[dst].bottom(2),
                      new_tip="never")
        p300.mix(3, 200, rack[dst].bottom(2))
        p300.drop_tip()

    # ---------------- 2. standards into the plate, in triplicate ----------------
    for col, tube in enumerate(SERIES_TUBES, start=1):
        for row in ROWS[:N_REPLICATES]:
            p300.pick_up_tip()
            p300.transfer(SAMPLE_VOL, rack[tube].bottom(2),
                          plate[f"{row}{col}"].bottom(1), new_tip="never")
            p300.drop_tip()

    # ---------------- 3. reaction mix into every used well ----------------
    for col in range(1, len(SERIES_TUBES) + 1):
        for row in ROWS[:N_REPLICATES]:
            p300.pick_up_tip()
            p300.transfer(REACTION_VOL, reaction, plate[f"{row}{col}"].bottom(1),
                          new_tip="never")
            p300.mix(2, 60, plate[f"{row}{col}"].bottom(1))
            p300.drop_tip()

    # ---------------- 4. the paper's 1 h dark incubation ----------------
    protocol.delay(minutes=60,
                   msg="Incubating 1 h at room temperature in the dark before the stop")

    # ---------------- 5. stop the reaction ----------------
    for col in range(1, len(SERIES_TUBES) + 1):
        for row in ROWS[:N_REPLICATES]:
            p300.pick_up_tip()
            p300.transfer(STOP_VOL, acetic, plate[f"{row}{col}"].bottom(1),
                          new_tip="never")
            p300.drop_tip()

    protocol.comment("Standard curve ready — read absorbance at 490 nm with 650 nm reference.")
