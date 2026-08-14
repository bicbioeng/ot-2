requirements = {"robotType": "OT-2", "apiLevel": "2.20"}

metadata = {
    "protocolName": "Pen-Strep and Plant Extract Dilution Series",
    "author": "Expert Opentrons Protocol Engineer",
    "description": "Performs plant extract dilution series in a 96-well plate using OT-2.",
}

def run(protocol):
    # 1. Load Labware
    tiprack_300 = protocol.load_labware("opentrons_96_tiprack_300ul", "1")
    reservoir = protocol.load_labware("nest_12_reservoir_15ml", "2")
    plate = protocol.load_labware("nest_96_wellplate_200ul_flat", "3")

    # 2. Load Pipette (using single-channel gen2 p300)
    pipette = protocol.load_instrument("p300_single_gen2", "right", tip_racks=[tiprack_300])

    # 3. Define Liquids
    stock_liquid = protocol.define_liquid(
        name="Piper betle plant extract stock solution",
        description="Stock solution of Piper betle plant extract",
        display_color="#FF8C00"
    )
    diluent_liquid = protocol.define_liquid(
        name="Cation-adjusted Mueller-Hinton broth (MHB) / DMEM",
        description="Diluent for serial dilution",
        display_color="#00FFFF"
    )

    # Load liquids into source wells on reservoir
    reservoir["A1"].load_liquid(liquid=stock_liquid, volume=10000)
    reservoir["A2"].load_liquid(liquid=diluent_liquid, volume=10000)

    # 4. Protocol Pause (Gate required for human intervention checkpoints)
    protocol.pause("Ensure reagents and plate are loaded correctly on deck before starting dilution.")

    # 5. Dilution Series Implementation (100 uL total per well)
    # A1 = 100% stock (100 uL stock)
    # A2-A8 = 2-fold serial dilutions (50 uL diluent + 50 uL transfer)
    
    # Step A1: Add 100 uL of stock to A1
    pipette.transfer(100, reservoir["A1"], plate["A1"], new_tip="always")

    # Add 50 uL diluent to wells A2 through A8
    diluent_destinations = [plate.wells_by_name()[f"A{i}"] for i in range(2, 9)]
    pipette.transfer(50, reservoir["A2"], diluent_destinations, new_tip="always")

    # Perform serial dilutions from A1 -> A2 -> A3 -> A4 -> A5 -> A6 -> A7 -> A8
    for i in range(1, 8):
        source_well = plate.wells_by_name()[f"A{i}"]
        dest_well = plate.wells_by_name()[f"A{i+1}"]
        
        pipette.aspirate(50, source_well)
        pipette.dispense(50, dest_well)
        pipette.mix(3, 50, dest_well)
        pipette.drop_tip()
