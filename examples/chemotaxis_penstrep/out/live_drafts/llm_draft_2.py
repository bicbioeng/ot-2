requirements = {"robotType": "OT-2", "apiLevel": "2.20"}

def run(protocol):
    # Load labware
    tiprack_300 = protocol.load_labware("opentrons_96_tiprack_300ul", "1")
    reservoir = protocol.load_labware("nest_12_reservoir_15ml", "2")
    plate = protocol.load_labware("nest_96_wellplate_200ul_flat", "3")

    # Load pipette
    p300 = protocol.load_instrument("p300_single_gen2", "right", tip_racks=[tiprack_300])

    # Define liquids
    stock_liquid = protocol.define_liquid(
        name="Piper betle plant extract stock solution",
        description="Plant extract stock solution",
        display_color="#4CAF50"
    )
    diluent_liquid = protocol.define_liquid(
        name="cation-adjusted Mueller-Hinton broth (MHB) / DMEM",
        description="Diluent broth",
        display_color="#2196F3"
    )

    # Load liquids into source reservoir wells
    reservoir["A1"].load_liquid(stock_liquid, 10000)
    reservoir["A2"].load_liquid(diluent_liquid, 10000)

    # Dilution series targets and volumes in 96-well plate (Row A, wells A1-A8)
    # A1: 100% v/v (100 uL stock)
    # A2-A8: 50%, 25%, 12%, 6%, 3%, 2%, 1% (50 uL diluent first, then serial transfer of 50 uL)
    
    dilution_wells = [plate.wells_by_name()[f"A{i}"] for i in range(1, 9)]

    # Step 1: Add 50 uL diluent to wells A2 through A8
    for well in dilution_wells[1:]:
        p300.transfer(50, reservoir["A2"], well, new_tip="always")

    # Step 2: Add 100 uL stock to well A1
    p300.transfer(100, reservoir["A1"], dilution_wells[0], new_tip="always")

    # Step 3: Perform 1:2 serial dilutions from A1 through A7 into A2 through A8 (50 uL transfers)
    for i in range(len(dilution_wells) - 1):
        source_well = dilution_wells[i]
        dest_well = dilution_wells[i + 1]
        p300.transfer(50, source_well, dest_well, mix_after=(3, 30), new_tip="always")

    # Final pause to fulfill protocol gating requirements
    protocol.pause("Dilution series complete. Proceed off-robot for incubation and analysis.")
