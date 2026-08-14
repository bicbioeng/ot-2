metadata = {
    "protocolName": "Pen-Strep Dilution Series - Piper betle extract",
    "author": "Opentrons Protocol Engineer",
    "description": "Performs aqueous liquid handling for a plant extract dilution series on the OT-2.",
}

requirements = {"robotType": "OT-2", "apiLevel": "2.20"}


def run(protocol):
    # Load labware
    reservoir = protocol.load_labware("nest_12_reservoir_15ml", "1")
    plate = protocol.load_labware("nest_96_wellplate_200ul_flat", "2")
    tiprack = protocol.load_labware("opentrons_96_tiprack_300ul", "3")

    # Load pipette (p300 single-channel GEN2)
    pipette = protocol.load_instrument("p300_single_gen2", "right", tip_racks=[tiprack])

    # Define liquids
    extract_stock = protocol.define_liquid(
        name="Piper betle plant extract stock solution",
        description="Stock solution of Piper betle plant extract",
        display_color="#FF8C00",
    )
    diluent = protocol.define_liquid(
        name="cation-adjusted Mueller-Hinton broth (MHB) / DMEM",
        description="Diluent for the dilution series",
        display_color="#00CED1",
    )

    # Assign liquids to source wells in the reservoir
    reservoir["A1"].load_liquid(extract_stock, volume=5000)
    reservoir["A2"].load_liquid(diluent, volume=10000)

    # Dilution series parameters
    # Total volume per well = 100 uL
    # A1: 100% v/v (100 uL stock, 0 uL diluent)
    # A2: 50% v/v (50 uL stock, 50 uL diluent)
    # A3: 25% v/v (25 uL stock, 75 uL diluent)
    # A4: 12% v/v (12 uL stock, 88 uL diluent)
    # A5: 6% v/v (6 uL stock, 94 uL diluent)
    # A6: 3% v/v (3 uL stock, 97 uL diluent)
    # A7: 2% v/v (2 uL stock, 98 uL diluent)
    # A8: 1% v/v (1 uL stock, 99 uL diluent)

    dest_wells = [
        plate.wells_by_name()[f"A{i}"] for i in range(1, 9)
    ]  # A1 through A8

    stock_volumes = [100, 50, 25, 12, 6, 3, 2, 1]
    diluent_volumes = [0, 50, 75, 88, 94, 97, 98, 99]

    # Step 1: Add diluent to wells A2-A8 (A1 gets 0 diluent)
    for i, dest in enumerate(dest_wells):
        d_vol = diluent_volumes[i]
        if d_vol > 0:
            pipette.pick_up_tip()
            pipette.transfer(
                d_vol,
                reservoir["A2"],
                dest,
                new_tip="never",
            )
            pipette.drop_tip()

    # Step 2: Add stock extract to wells A1-A8 with fresh tip for every destination
    for i, dest in enumerate(dest_wells):
        s_vol = stock_volumes[i]
        pipette.pick_up_tip()
        pipette.transfer(
            s_vol,
            reservoir["A1"],
            dest,
            new_tip="never",
        )
        pipette.drop_tip()
