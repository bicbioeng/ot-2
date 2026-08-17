"""Gate a ledger before it reaches the sim, and print the deck it describes.

`opentrons analyze` exits 0 even when the protocol failed — the verdict lives
inside the JSON. Checking the exit code alone would happily stream a broken run.
Kept as its own file (not a heredoc) because nested heredoc quoting over ssh
silently mangles scripts.
"""
import json
import sys

j = json.load(open(sys.argv[1]))
errs = j.get("errors") or []
if j.get("result") != "ok" or errs:
    print(f"PROTOCOL NOT RUNNABLE (result={j.get('result')}, {len(errs)} error(s)):")
    for e in errs[:5]:
        print("   -", e.get("detail") if isinstance(e, dict) else e)
    sys.exit(1)

print(f"    ok -- {len(j.get('commands', []))} commands")
for p in j.get("pipettes", []):
    print(f"    pipette  {str(p.get('mount')):<5} {p.get('pipetteName')}")
for lw in sorted(j.get("labware", []),
                 key=lambda x: str(x.get("location", {}).get("slotName"))):
    slot = lw.get("location", {}).get("slotName")
    print(f"    slot {str(slot):<3} {lw.get('loadName')}")
