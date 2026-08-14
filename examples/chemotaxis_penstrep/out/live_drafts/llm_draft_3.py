requirements = {"robotType": "OT-2", "apiLevel": "2.20"}


def run(protocol):
    # Labware loading
    tiprack_300 = protocol.load_labware("opentrons_96_tiprack_300ul", "1")
    reservoir = protocol.load_labware("nest_12_reservoir_15ml", "2")
    plate = protocol.load_labware("nest_96_wellplate_200ul_flat", "3")

    # Pipette loading
    pipette = protocol.load_instrument(
        "p300_single_gen2", "right", tip_racks=[tiprack_300]
    )

    # Liquid definitions
    stock_liquid = protocol.define_liquid(
        name="Piper betle plant extract stock solution",
        description="Stock solution for dilution series",
        display_color="#FF8C00",
    )
    diluent_liquid = protocol.define_liquid(
        name="Cation-adjusted Mueller-Hinton broth (MHB) / DMEM",
        description="Diluent for dilution series",
        display_color="#00FFFF",
    )

    # Assign liquids to source wells
    reservoir["A1"].load_liquid(stock_liquid, 10000)
    reservoir["A2"].load_liquid(diluent_liquid, 10000)

    # Dilution Series Strategy (100 uL total per well in A1 through A8):
    # A1 = 100% stock -> 100 uL of stock directly into A1
    # A2-A8 = Serial dilution setup
    # First, add 50 uL of diluent to wells A2 through A8
    # Then, perform serial transfer: 50 uL from A1 to A2, mix, 50 uL from A2 to A3, mix, etc.
    # Alternatively, perform precise volume distribution as specified by standard v/v fractions:
    # A1: 100 uL stock
    # A2: 50 uL stock + 50 uL diluent (50%)
    # A3: 25 uL stock + 75 uL diluent (25%) -> or 50 uL from A2 (50%) + 50 uL diluent = 25%
    # A4: 12% v/v (approx 12.5 uL stock equivalent) -> serial step: 50 uL from A3 + 50 uL diluent
    # A5: 6% v/v -> serial step: 50 uL from A4 + 50 uL diluent
    # A6: 3% v/v -> serial step: 50 uL from A5 + 50 uL diluent
    # A7: 2% v/v -> Wait, let's look at standard 2-fold vs specified fractions:
    # Targets: A1=100%, A2=50%, A3=25%, A4=12%, A5=6%, A6=3%, A7=2%, A8=1%
    # Let's dispense exact volumes of stock and diluent to each well to match the exact targets,
    # keeping total volume at 100 uL per well.
    # A1: 100 uL stock, 0 uL diluent
    # A2: 50 uL stock, 50 uL diluent
    # A3: 25 uL stock, 75 uL diluent
    # A4: 12 uL stock, 88 uL diluent (or 12.5 uL if precision allows, but let's use 12 uL or 12.5 uL)
    # Spec says: A1=100%, A2=50%, A3=25%, A4=12%, A5=6%, A6=3%, A7=2%, A8=1%
    # Let's calculate exact volumes for 100 uL total:
    # A1: 100 uL stock
    # A2: 50 uL stock, 50 uL diluent
    # A3: 25 uL stock, 75 uL diluent
    # A4: 12 uL stock, 88 uL diluent
    # A5: 6 uL stock, 94 uL diluent
    # A6: 3 uL stock, 97 uL diluent
    # A7: 2 uL stock, 98 uL diluent
    # A8: 1 uL stock, 99 uL diluent

    stock_volumes = [100, 50, 25, 12, 6, 3, 2, 1]
    diluent_volumes = [0, 50, 75, 88, 94, 97, 98, 99]
    wells = [
        plate.wells_by_name()[f"A{i}"] for i in range(1, 9)
    ]  # A1 through A8

    protocol.pause("Ready to begin Pen-Strep dilution series preparation.")

    for i, well in enumerate(wells):
        s_vol = stock_volumes[i]
        d_vol = diluent_volumes[i]

        # Add diluent first if needed (using fresh tip)
        if d_vol > 0:
            pipette.pick_up_tip()
            pipette.transfer(
                d_vol,
                reservoir["A2"],
                well,
                new_tip="never",
                air_gap=5,
                mix_after=(3, 50),
            )
            pipette.drop_tip()

        # Add stock (using fresh tip)
        if s_vol > 0:
            pipette.pick_up_tip()
            pipette.transfer(
                s_vol,
                reservoir["A1"],
                well,
                new_tip="never",
                air_gap=5,
                mix_after=(3, 50 if s_vol + d_vol >= 50 else s_vol),
            )
            pipette.drop_tip()
