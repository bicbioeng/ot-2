from opentrons import protocol_api

requirements = {"robotType": "OT-2", "apiLevel": "2.20"}


def run(protocol: protocol_api.ProtocolContext):
    # Define liquids
    pen_strep = protocol.define_liquid(
        name="Penicillin-Streptomycin Stock",
        description="Pen-Strep stock solution",
        display_color="#FF0000",
    )
    lb_media = protocol.define_liquid(
        name="LB media", description="LB media diluent", display_color="#0000FF"
    )

    # Load labware
    reservoir = protocol.load_labware("nest_12_reservoir_15ml", "1")
    tiprack_300 = protocol.load_labware("opentrons_96_tiprack_300ul", "2")
    plate = protocol.load_labware("corning_12_wellplate_6.9ml_flat", "3")

    # Load source liquids
    reservoir["A1"].load_liquid(pen_strep, volume=10000)
    reservoir["A2"].load_liquid(lb_media, volume=10000)

    # Load pipette
    p300 = protocol.load_instrument(
        "p300_single_gen2", mount="left", tip_racks=[tiprack_300]
    )

    # LB Media transfers (split into <= 300 uL chunks)
    # A1: 1000 uL LB (0% stock) -> 4 x 250 uL
    # A2: 850 uL LB (15% stock) -> 300 uL + 300 uL + 250 uL
    # A3: 750 uL LB (25% stock) -> 3 x 250 uL
    lb_transfers = [
        ("A1", [250.0, 250.0, 250.0, 250.0]),
        ("A2", [300.0, 300.0, 250.0]),
        ("A3", [250.0, 250.0, 250.0]),
    ]

    for dest_well, vols in lb_transfers:
        for vol in vols:
            p300.transfer(
                vol,
                reservoir["A2"],
                plate[dest_well],
                new_tip="always",
            )

    # Stock transfers
    # A2: 150 uL stock
    # A3: 250 uL stock
    stock_transfers = [
        ("A2", 150.0),
        ("A3", 250.0),
    ]

    for dest_well, vol in stock_transfers:
        p300.transfer(
            vol,
            reservoir["A1"],
            plate[dest_well],
            new_tip="always",
        )

    # Pause for off-robot downstream steps / Gate G1
    protocol.pause("G1: Pen-Strep dilution series complete.")
