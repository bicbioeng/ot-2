requirements = {"robotType": "OT-2", "apiLevel": "2.20"}

metadata = {
    "protocolName": "Pen-Strep Dilution Series",
    "author": "Opentrons Protocol Engineer",
    "description": "Prepares a Pen-Strep dilution series (0%, 15%, 25% v/v) in a 24-well plate.",
}


def run(protocol):
    # Load tip rack
    tiprack_300 = protocol.load_labware("opentrons_96_tiprack_300ul", "1")

    # Load labware
    reservoir = protocol.load_labware("nest_12_reservoir_15ml", "2")
    plate = protocol.load_labware("corning_24_wellplate_3.4ml_flat", "3")

    # Load pipette
    p300 = protocol.load_instrument(
        "p300_single_gen2", mount="left", tip_racks=[tiprack_300]
    )

    # Define liquids
    penstrep = protocol.define_liquid(
        name="PenStrep 100x stock",
        description="PenStrep stock solution",
        display_color="#FF5733",
    )
    lb_broth = protocol.define_liquid(
        name="LB broth",
        description="LB broth diluent",
        display_color="#33FF57",
    )

    # Load liquids into source reservoir
    reservoir["A1"].load_liquid(penstrep, volume=2000)
    reservoir["A2"].load_liquid(lb_broth, volume=10000)

    # Transfer diluent (LB broth) to target wells
    diluent_volumes = {"A1": 200, "A2": 170, "A3": 150}
    for well_name, vol in diluent_volumes.items():
        p300.transfer(
            vol,
            reservoir["A2"],
            plate[well_name],
            new_tip="always",
        )

    # Transfer stock (PenStrep) to target wells
    stock_volumes = {"A2": 30, "A3": 50}
    for well_name, vol in stock_volumes.items():
        p300.transfer(
            vol,
            reservoir["A1"],
            plate[well_name],
            new_tip="always",
            mix_after=(3, 100),
        )
