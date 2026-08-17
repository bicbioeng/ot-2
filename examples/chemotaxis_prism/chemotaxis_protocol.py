requirements = {"robotType": "OT-2"}
from opentrons import protocol_api

metadata = {
    "protocolName": "Chemotaxis Agar and Culture Loading",
    "author": "PRISM",
    "description": "Loads PenStrep-agar mixtures and E. coli cultures into a 12-well chemotaxis assay plate",
    "apiLevel": "2.12",
    "info": "Bacterial chemotaxis / drug-repellent assay plate preparation written by PRISM",
    "name": "Chemotaxis Agar and Culture Loading",
    "version": "1.0"
}

def run(protocol: protocol_api.ProtocolContext):
    deck = {}
    pipettes = {}

    ################
    # load labware #
    ################
    # Deck 1: 12-well assay plate (the experiment plate)
    deck["1"] = protocol.load_labware("corning_12_wellplate_6.9ml_flat", "1")
    # Deck 2: 15-tube rack with agar mixtures (A1/A2/A3) and bacterial cultures (B1/B2)
    deck["2"] = protocol.load_labware("opentrons_15_tuberack_falcon_15ml_conical", "2")
    # Deck 7: 300 uL tip rack
    deck["7"] = protocol.load_labware("opentrons_96_tiprack_300ul", "7")
    pipettes["left"] = protocol.load_instrument("p300_single_gen2", "left", tip_racks=[deck["7"]])

    # Reagent tubes on the 15-tube rack
    penstrep_agar_15 = deck["2"]["A1"]   # 15% PenStrep-Agar, 37 C
    penstrep_agar_25 = deck["2"]["A2"]   # 25% PenStrep-Agar, 37 C
    agar_only = deck["2"]["A3"]          # 8% agar alone (control), 37 C
    culture_dh5a = deck["2"]["B1"]       # E. coli DH5-alpha diluted culture
    culture_wdcm = deck["2"]["B2"]       # E. coli WDCM 00012 diluted culture

    ####################
    # execute commands #
    ####################

    ###############################################################
    # Phase 1: load 200 uL of agar mixture into all 12 wells
    ###############################################################
    agar_loading = [
        # (source tube, destination well)
        (penstrep_agar_15, "A1"),   # 1.)  15% PenStrep-Agar
        (penstrep_agar_15, "A2"),   # 2.)  15% PenStrep-Agar
        (penstrep_agar_15, "A3"),   # 3.)  15% PenStrep-Agar
        (penstrep_agar_15, "A4"),   # 4.)  15% PenStrep-Agar
        (penstrep_agar_25, "B1"),   # 5.)  25% PenStrep-Agar
        (penstrep_agar_25, "B2"),   # 6.)  25% PenStrep-Agar
        (penstrep_agar_25, "B3"),   # 7.)  25% PenStrep-Agar
        (penstrep_agar_25, "B4"),   # 8.)  25% PenStrep-Agar
        (agar_only, "C1"),          # 9.)  8% agar-only control
        (agar_only, "C2"),          # 10.) 8% agar-only control
        (agar_only, "C3"),          # 11.) 8% agar-only control
        (agar_only, "C4"),          # 12.) 8% agar-only control
    ]

    for source, well in agar_loading:
        pipettes["left"].pick_up_tip()
        pipettes["left"].well_bottom_clearance.aspirate = 1
        pipettes["left"].aspirate(200.0, source)
        pipettes["left"].well_bottom_clearance.dispense = 1
        pipettes["left"].dispense(200.0, deck["1"][well])
        pipettes["left"].blow_out()
        pipettes["left"].drop_tip()

    ###############################################################
    # Phase 2: 13.) wait for the agar to solidify at room temperature
    ###############################################################
    protocol.delay(minutes=15, msg="Allowing agar to solidify in all 12 wells")

    ###############################################################
    # Phase 3: overlay 200 uL of bacterial culture onto every well
    ###############################################################
    culture_loading = [
        # (source tube, destination well)
        (culture_dh5a, "A1"),   # 14.) E. coli DH5-alpha
        (culture_dh5a, "A2"),   # 15.) E. coli DH5-alpha
        (culture_dh5a, "B1"),   # 16.) E. coli DH5-alpha
        (culture_dh5a, "B2"),   # 17.) E. coli DH5-alpha
        (culture_dh5a, "C1"),   # 18.) E. coli DH5-alpha
        (culture_dh5a, "C2"),   # 19.) E. coli DH5-alpha
        (culture_wdcm, "A3"),   # 20.) E. coli WDCM 00012
        (culture_wdcm, "A4"),   # 21.) E. coli WDCM 00012
        (culture_wdcm, "B3"),   # 22.) E. coli WDCM 00012
        (culture_wdcm, "B4"),   # 23.) E. coli WDCM 00012
        (culture_wdcm, "C3"),   # 24.) E. coli WDCM 00012
        (culture_wdcm, "C4"),   # 25.) E. coli WDCM 00012
    ]

    for source, well in culture_loading:
        pipettes["left"].pick_up_tip()
        pipettes["left"].well_bottom_clearance.aspirate = 1
        pipettes["left"].aspirate(200.0, source)
        pipettes["left"].well_bottom_clearance.dispense = 1
        pipettes["left"].dispense(200.0, deck["1"][well])
        pipettes["left"].blow_out()
        pipettes["left"].drop_tip()
