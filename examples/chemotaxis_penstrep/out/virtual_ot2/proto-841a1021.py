requirements = {"robotType": "OT-2", "apiLevel": "2.20"}


def run(protocol):
    # Labware
    reservoir = protocol.load_labware("nest_12_reservoir_15ml", "1")
    plate = protocol.load_labware("corning_24_wellplate_3.4ml_flat", "2")
    tiprack_300 = protocol.load_labware("opentrons_96_tiprack_300ul", "3")

    # Pipette
    p300 = protocol.load_instrument(
        "p300_single_gen2", mount="left", tip_racks=[tiprack_300]
    )

    # Declare Liquids
    pen_strep = protocol.define_liquid(
        name="PenStrep 100x stock",
        description="PenStrep 100x stock solution",
        display_color="#FF4500",
    )
    lb_broth = protocol.define_liquid(
        name="LB broth",
        description="LB broth diluent",
        display_color="#1E90FF",
    )

    # Load Liquids into Source Reservoir
    reservoir["A1"].load_liquid(pen_strep, volume=1000)
    reservoir["A2"].load_liquid(lb_broth, volume=5000)

    # 1. Transfer Diluent (LB broth) to wells A1, A2, A3
    # A1: 200 uL LB (0% stock)
    # A2: 170 uL LB (15% stock -> 30 uL stock)
    # A3: 150 uL LB (25% stock -> 50 uL stock)
    diluent_transfers = [
        (plate["A1"], 200),
        (plate["A2"], 170),
        (plate["A3"], 150),
    ]

    for well, vol in diluent_transfers:
        p300.transfer(
            vol,
            reservoir["A2"],
            well,
            new_tip="always",
        )

    # 2. Transfer Stock (PenStrep) to wells A2, A3
    stock_transfers = [
        (plate["A2"], 30),
        (plate["A3"], 50),
    ]

    for well, vol in stock_transfers:
        p300.transfer(
            vol,
            reservoir["A1"],
            well,
            new_tip="always",
            mix_after=(3, 100),
        )
