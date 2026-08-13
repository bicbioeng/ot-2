# Captured `opentrons analyze` contract (M1)

- **opentrons**: `8.8.2`  ·  **python**: `3.10.20`  ·  **MAX apiLevel**: `2.27`
- **invocation**: `python -m opentrons.cli analyze --json-output - [--check] [--rtp-values '{...}'] PROTOCOL.py [labware.json ...]`

## Exit codes & result (observed)

| fixture | result | exit (no --check) | exit (--check) | errors |
|---|---|---|---|---|
| good_minimal | `ok` | 0 | 0 | 0 |
| good_dilution | `ok` | 0 | 0 | 0 |
| bad_overaspirate | `not-ok` | 0 | 255 | 1 |

## ErrorOccurrence shape (bad fixture)

- keys=`['createdAt', 'detail', 'errorCode', 'errorInfo', 'errorType', 'id', 'isDefined', 'wrappedErrors']` type=`ExceptionInProtocolError` code=`4000` wrapped=True
  - detail: ProtocolCommandFailedError [line 18]: Error 4000 GENERAL_ERROR (ProtocolCommandFailedError): InvalidAspirateVolumeError: Cannot aspirate 400.0 µL when only 300 

## Library verification

- labware OK: ['opentrons_96_tiprack_300ul', 'opentrons_96_tiprack_20ul', 'opentrons_96_tiprack_1000ul', 'nest_12_reservoir_15ml', 'corning_24_wellplate_3.4ml_flat', 'corning_12_wellplate_6.9ml_flat', 'nest_96_wellplate_200ul_flat']
- labware MISSING: (none)
- pipettes OK: ['p20_single_gen2', 'p300_single_gen2', 'p1000_single_gen2']
- pipettes MISSING: (none)
