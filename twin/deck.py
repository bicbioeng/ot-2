"""Exact OT-2 deck + labware geometry — NO hand-typed pitches or approximations.

Every coordinate is sourced from real Opentrons definitions:
  * labware  -> the definition embedded in each analysis.json `loadLabware`
               result (`result.definition`): exact per-well x/y/z, depth, and
               shape. The ledger is self-describing; the twin never guesses a
               well position.
  * deck slots -> the real `ot2_standard` deck definition, exported once to
               twin/decks/ot2_standard.json (from opentrons_shared_data).

Coordinates are Opentrons deck frame: x left->right, y front->back, z up, in mm.
A well's (x,y) is its center from the labware corner; its `z` is the well-bottom
height from the labware bottom, so the rim height is z + depth.

This module is intentionally paper-agnostic: give it any protocol's ledger and
it reproduces that protocol's exact deck. Modules (which add a z offset under a
labware) are not yet modelled — a labware on a module raises, rather than being
silently placed at slot height. Nothing here is assumed.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_DECKS = Path(__file__).resolve().parent / "decks"
_REACH_MARGIN = 15.0        # mm the pipette can travel beyond the deck slot extent
TRASH_SLOT = "12"


def load_deck(name: str = "ot2_standard") -> dict[str, dict]:
    """Return {slot -> {'position':[x,y,z], 'boundingBox':{...}}} from the real def."""
    p = _DECKS / f"{name}.json"
    if not p.exists():
        raise FileNotFoundError(
            f"deck definition {p} missing — export it from opentrons_shared_data "
            f"(see twin/README.md). The twin will not guess slot offsets.")
    return json.loads(p.read_text())["slots"]


def deck_extent(slots: dict[str, dict]) -> tuple[float, float, float, float]:
    """(x_min, x_max, y_min, y_max) of the addressable deck, from real slot boxes."""
    xs0 = [s["position"][0] for s in slots.values()]
    ys0 = [s["position"][1] for s in slots.values()]
    xs1 = [s["position"][0] + s["boundingBox"]["xDimension"] for s in slots.values()]
    ys1 = [s["position"][1] + s["boundingBox"]["yDimension"] for s in slots.values()]
    return min(xs0), max(xs1), min(ys0), max(ys1)


@dataclass
class LabwareGeom:
    """A thin, exact view over an Opentrons labware definition dict."""
    definition: dict

    @property
    def load_name(self) -> str:
        return self.definition["parameters"]["loadName"]

    @property
    def is_tiprack(self) -> bool:
        return bool(self.definition["parameters"].get("isTiprack"))

    @property
    def dims(self) -> tuple[float, float, float]:
        d = self.definition["dimensions"]
        return d["xDimension"], d["yDimension"], d["zDimension"]

    @property
    def corner(self) -> tuple[float, float, float]:
        c = self.definition.get("cornerOffsetFromSlot") or {}
        return c.get("x", 0.0), c.get("y", 0.0), c.get("z", 0.0)

    def well_names(self) -> list[str]:
        return list(self.definition["wells"].keys())

    def _well(self, name: str) -> dict:
        try:
            return self.definition["wells"][name]
        except KeyError as e:
            raise KeyError(
                f"well {name!r} not in {self.load_name} definition — refusing to "
                f"guess its position") from e

    def well_offset(self, name: str) -> tuple[float, float]:
        w = self._well(name)
        return w["x"], w["y"]

    def well_rim_offset_z(self, name: str) -> float:
        w = self._well(name)
        return w["z"] + w["depth"]           # well bottom + depth = rim

    def well_radius(self, name: str) -> float:
        w = self._well(name)
        if w.get("shape") == "circular":
            return w["diameter"] / 2
        return min(w.get("xDimension", 6.0), w.get("yDimension", 6.0)) / 2


def well_deck_xyz(slot_pos: list[float], geom: LabwareGeom, well: str) -> tuple[float, float, float]:
    """Absolute deck (x, y, rim_z) of a well, from real slot + real labware def."""
    cx, cy, cz = geom.corner
    wx, wy = geom.well_offset(well)
    x = slot_pos[0] + cx + wx
    y = slot_pos[1] + cy + wy
    z = slot_pos[2] + cz + geom.well_rim_offset_z(well)
    return x, y, z


def slot_center_top(slot_pos: list[float], bbox: dict) -> tuple[float, float, float]:
    return (slot_pos[0] + bbox["xDimension"] / 2,
            slot_pos[1] + bbox["yDimension"] / 2,
            slot_pos[2])


def reachable(x: float, y: float, slots: dict[str, dict]) -> bool:
    x0, x1, y0, y1 = deck_extent(slots)
    return (x0 - _REACH_MARGIN <= x <= x1 + _REACH_MARGIN
            and y0 - _REACH_MARGIN <= y <= y1 + _REACH_MARGIN)
