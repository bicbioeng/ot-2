from opentrons import protocol_api

requirements = {"robotType": "OT-2", "apiLevel": "2.20"}

metadata = {
    "protocolName": "Pen-Strep Dilution Series",
    "author": "Opentrons Protocol Engineer",
    "description": "Performs a plant extract dilution series in a 96-well plate using a 12-channel reservoir.",
}


def run(protocol: protocol_api.ProtocolContext):
    # Load labware
    reservoir = protocol.load_labware("nest_12_reservoir_15ml", "1")
    plate = protocol.load_labware("nest_96_wellplate_200ul_flat", "2")
    tiprack_300 = protocol.load_labware("opentrons_96_tiprack_300ul", "3")

    # Load pipette
    pipette = protocol.load_instrument(
        "p300_single_gen2", "right", tip_racks=[tiprack_300]
    )

    # Define liquids
    stock_liquid = protocol.define_liquid(
        name="Piper betle plant extract stock solution",
        description="Stock solution for dilution series",
        display_color="#FF0000",
    )
    diluent_liquid = protocol.define_liquid(
        name="cation-adjusted Mueller-Hinton broth (MHB) / DMEM",
        description="Diluent for serial dilution",
        display_color="#0000FF",
    )

    # Load liquids into source wells in the reservoir
    reservoir["A1"].load_liquid(stock_liquid, 10000)
    reservoir["A2"].load_liquid(diluent_liquid, 10000)

    # Pause at gate as required by the validation system
    protocol.pause("Setup complete. Ready to begin liquid handling.")

    # Dilution Series Volumes (in uL) for 100 uL total per well
    # A1: 100% stock -> 100 uL stock, 0 uL diluent
    # A2: 50% stock -> 50 uL stock, 50 uL diluent
    # A3: 25% stock -> 25 uL stock, 75 uL diluent
    # A4: 12% stock -> 12 uL stock, 88 uL diluent
    # A5: 6% stock -> 6 uL stock, 94 uL diluent
    # A6: 3% stock -> 3 uL stock, 97 uL diluent
    # A7: 2% stock -> 2 uL stock, 98 uL diluent
    # A8: 1% stock -> 1 uL stock, 99 uL diluent

    wells = ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8"]
    stock_volumes = [100, 50, 25, 12, 6, 3, 2, 1]
    diluent_volumes = [0, 50, 75, 88, 94, 97, 98, 99]

    # Dispense diluent first (where volume > 0)
    for well_name, vol in zip(wells, diluent_volumes):
        if vol > 0:
            pipette.transfer(
                vol,
                reservoir["A2"],
                plate[well_name],
                new_tip="always",
            )

    # Dispense stock extract next
    for well_name, vol in zip(wells, stock_volumes):
        if vol > 0:
            pipette.transfer(
                vol,
                reservoir["A1"],
                plate[well_name],
                new_tip="always",
            )
