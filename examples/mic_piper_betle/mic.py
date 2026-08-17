requirements = {"robotType": "OT-2"}
from opentrons import protocol_api

metadata = {
    "protocolName": "MIC of Piper betle extract against multidrug-resistant bacteria",
    "author": "paper2protocol",
    "description": (
        "Broth microdilution MIC (CLSI M07-A8) replicating Bernardo et al., "
        "PLOS ONE 11(1):e0146349 (2016), doi:10.1371/journal.pone.0146349. "
        "Thirteen-point two-fold series of Piper betle extract in cation-adjusted "
        "Mueller-Hinton broth spanning 10,000 down to 2.44 ug/mL; 10 uL of adjusted "
        "inoculum into each well containing 100 uL of extract; triplicate throughout."
    ),
    "apiLevel": "2.12",
}

# ---------------------------------------------------------------------------
# FROM THE PAPER (Materials and methods -> "Broth Microdilution Method"), quoted:
#   "Two-fold serial dilution of each plant extract with starting concentration
#    of 100 mg/ml was prepared using cation-adjusted Mueller-Hinton broth or MHB
#    ... as diluent resulting in concentrations of 2.44 ug/ml to 10,000 ug/ml."
#   "Each set-up was carried out in triplicate in sterile 96-well microplates."
#   "Controls consisted of culture control (no plant extract), negative control
#    (plant extract and MHB only) and reference drug controls."
#   "Ten (10) uL of the adjusted inoculum were added into each well containing
#    100 uL of plant extract in the dilution series, and mixed."
#
# 10,000 -> 2.44 ug/mL halving is exactly 13 points (10,000 / 2^12 = 2.4414).
#
# WHY TWO PIPETTES — a real constraint, not a preference:
#   The p300_single_gen2 has a manufacturer minimum of 20 uL. The paper's 10 uL
#   inoculum is HALF that. `opentrons analyze` accepts a 10 uL p300 aspirate
#   without complaint, so the deterministic gate does NOT catch this; it would
#   simply be dispensed inaccurately on the bench. The inoculum therefore goes
#   on a p20_single_gen2 (1-20 uL), and scripts/replication_check.py now fails
#   any transfer below its pipette's rated minimum.
#
# IMPLEMENTATION DECISIONS (NOT from the paper — flagged for sign-off):
#   * Tube A1 is preloaded by the operator with extract at 10,000 ug/mL (the top
#     of the series). The paper's 100 mg/mL figure is the crude stock; the
#     series it reports begins at 10,000 ug/mL (= 10 mg/mL).
#   * 700 uL equal-volume dilution steps, leaving >=300 uL per concentration.
#   * Plate layout below; the paper fixes only "triplicate".
#   * Fresh p20 tip per concentration so no extract is carried between
#     concentrations, dispensing above the liquid surface.
#   * Reference-drug controls are emitted as a handoff: the paper does not give
#     the reference antibiotic's own dilution series.
#
# NOTE ON REPORTED vs FINAL CONCENTRATION: adding 10 uL of inoculum to 100 uL of
# extract dilutes it by 110/100, so the in-well concentration is 0.909x the
# series value. The paper reports the series values; we realize the series
# values. Worth confirming at sign-off.
# ---------------------------------------------------------------------------

TOP_CONC = 10000.0        # ug/mL, top of the series
N_POINTS = 13             # 10,000 -> 2.4414 ug/mL
EXTRACT_VOL = 100.0       # uL of extract per well
INOCULUM_VOL = 10.0       # uL  <- below p300 minimum; p20 required
N_REPLICATES = 3          # "in triplicate"
SERIES_VOL = 700.0        # uL per dilution step (implementation choice)

CONCENTRATIONS = [TOP_CONC / (2 ** i) for i in range(N_POINTS)]

# 15-tube rack: 13 series positions + diluent + inoculum == exactly 15
SERIES_TUBES = ["A1", "A2", "A3", "A4", "A5",
                "B1", "B2", "B3", "B4", "B5",
                "C1", "C2", "C3"]
MHB_TUBE = "C4"
INOCULUM_TUBE = "C5"

REP_ROWS = ["A", "B", "C"]        # the three replicates
BLOCK2_ROWS = ["E", "F", "G"]     # 13th concentration + controls
COL_13TH = 1
COL_CULTURE_CTRL = 3              # no plant extract
COL_NEG_CTRL = 5                  # plant extract + MHB only, no inoculum


def run(protocol: protocol_api.ProtocolContext):
    plate = protocol.load_labware("corning_96_wellplate_360ul_flat", "1")
    rack = protocol.load_labware("opentrons_15_tuberack_falcon_15ml_conical", "2")
    tips300 = protocol.load_labware("opentrons_96_tiprack_300ul", "7")
    tips20 = protocol.load_labware("opentrons_96_tiprack_20ul", "8")

    p300 = protocol.load_instrument("p300_single_gen2", "left", tip_racks=[tips300])
    p20 = protocol.load_instrument("p20_single_gen2", "right", tip_racks=[tips20])

    for pip in (p300, p20):
        pip.well_bottom_clearance.aspirate = 1
        pip.well_bottom_clearance.dispense = 1

    mhb = rack[MHB_TUBE]
    inoculum = rack[INOCULUM_TUBE]
    series = [rack[t] for t in SERIES_TUBES]

    def well_for(index):
        """Plate well for concentration `index`, replicate `rep` — 13 points do not
        fit one 12-column block, so the 13th sits in a second block."""
        out = []
        if index < 12:
            for row in REP_ROWS:
                out.append(f"{row}{index + 1}")
        else:
            for row in BLOCK2_ROWS:
                out.append(f"{row}{COL_13TH}")
        return out

    ###########################################################################
    # Phase 1 - thirteen-point two-fold series in cation-adjusted MHB.
    ###########################################################################
    p300.pick_up_tip()
    for tube in series[1:]:
        left = SERIES_VOL
        while left > 0:
            v = min(left, p300.max_volume)
            p300.aspirate(v, mhb)
            p300.dispense(v, tube)
            left -= v
    p300.drop_tip()

    for i in range(len(series) - 1):
        p300.pick_up_tip()
        left = SERIES_VOL
        while left > 0:
            v = min(left, p300.max_volume)
            p300.aspirate(v, series[i])
            p300.dispense(v, series[i + 1])
            left -= v
        p300.mix(3, 200, series[i + 1])
        p300.drop_tip()

    ###########################################################################
    # Phase 2 - 100 uL of extract into each replicate well, plus the
    # negative control (extract, no inoculum) at the top concentration.
    ###########################################################################
    for idx, tube in enumerate(series):
        p300.pick_up_tip()
        for well in well_for(idx):
            p300.aspirate(EXTRACT_VOL, tube)
            p300.dispense(EXTRACT_VOL, plate[well])
        if idx == 0:                       # negative control uses the top concentration
            for row in BLOCK2_ROWS:
                p300.aspirate(EXTRACT_VOL, tube)
                p300.dispense(EXTRACT_VOL, plate[f"{row}{COL_NEG_CTRL}"])
        p300.drop_tip()

    ###########################################################################
    # Phase 3 - culture control: MHB in place of the extract.
    ###########################################################################
    p300.pick_up_tip()
    for row in BLOCK2_ROWS:
        p300.aspirate(EXTRACT_VOL, mhb)
        p300.dispense(EXTRACT_VOL, plate[f"{row}{COL_CULTURE_CTRL}"])
    p300.drop_tip()

    ###########################################################################
    # Phase 4 - 10 uL adjusted inoculum into every experimental well and the
    # culture control. p20, because 10 uL is below the p300's 20 uL minimum.
    # The negative control deliberately receives none.
    ###########################################################################
    for idx in range(len(series)):
        p20.pick_up_tip()                  # fresh tip per concentration
        for well in well_for(idx):
            p20.aspirate(INOCULUM_VOL, inoculum)
            p20.dispense(INOCULUM_VOL, plate[well])
        p20.drop_tip()

    p20.pick_up_tip()
    for row in BLOCK2_ROWS:
        p20.aspirate(INOCULUM_VOL, inoculum)
        p20.dispense(INOCULUM_VOL, plate[f"{row}{COL_CULTURE_CTRL}"])
    p20.drop_tip()

    ###########################################################################
    # Handoff gates - outside a liquid handler's scope.
    ###########################################################################
    protocol.comment(
        "HANDOFF: seal trays; incubate 16-20 h at 35 +/- 2 C in ambient air. "
        "MIC = lowest concentration with no growth vs the culture control."
    )
    protocol.comment(
        "HANDOFF: MBC - subculture each no-growth well with a 10 uL loop onto 5% sheep "
        "blood agar, 16-20 h at 35 +/- 2 C."
    )
    protocol.comment(
        "HANDOFF: reference-drug controls - the paper does not report the reference "
        "antibiotic's dilution series, so it is not reproduced here."
    )
