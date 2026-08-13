# OT-2 3D assets — provenance

Real, sourced assets — nothing fabricated. Each entry records where it came from, its exact
byte size / hash, and the **verified** licensing terms. All GitHub facts below were confirmed
against the live GitHub API (git tree + `/license` endpoint), and every local file was
independently re-hashed and its geometry re-measured (2026-08-06 verification sweep).

## ⚠ License status — corrected after verification

A prior assumption that the `Opentrons/ot2` CAD is Apache-2.0 is **REFUTED**: the repo has **no
LICENSE file** — GitHub's `/license` API returns 404 and the repo's `license` field is `null`.
So the OT-2 reference CAD is **UNSPECIFIED / all-rights-reserved by default**, softened only by
the repo README's explicit grant that Opentrons provides these files "for our community to modify
their OT-2 robots however they choose." We rely on that README grant for **research/visualization
use**; anyone reusing these assets should not assume an OSI license. (The *separate*
`Opentrons/otone_hardware` repo — the older OT-One — **is** Apache-2.0; do not conflate the two.)

## ot2/ot2_reference_detailed.stl  — PRIMARY (full robot)

- **Source:** `Opentrons/ot2` (branch `master`), path
  `reference-model/STL/OT-2 Reference Model Detailed.STL`
  (https://github.com/Opentrons/ot2/tree/master/reference-model/STL).
- **What it is:** the official OT-2 "Reference Model (Detailed)" — the **complete robot**:
  enclosure + rounded corner posts + windows, the X-gantry rail, the Z-axis pipette carriage
  with pipettes, and the deck plate with its slot grid. **42,172 triangles / 126,516 vertices**,
  real millimetres. External AABB **624.3 × 662.0 × 567.5 mm** (matches the physical OT-2:
  Opentrons specs list 66 × 57 × 63 cm incl. door/handles).
- **Downloaded:** 2026-08-06. **Size:** 2,108,684 bytes.
  **sha256:** `547f4866956b28fa0b6757572e1e36944a4a4127ca75ad25cc20e60edf339089`.
- **Use here:** the low-opacity **glass shell** — the real robot as visual context — with the
  twin's functional deck/labware/pipette rendered opaque and legible inside it. Non-colliding;
  it never changes a coordinate. Deck-frame alignment (analytically derived, not guessed) in
  `ot2/alignment.json`.

## ot2/ot2_reference_basic.stl  — fallback (coarse envelope)

- **Source:** same repo, `reference-model/STL/OT-2 Reference Model Basic.STL`.
- **What it is:** simplified full-robot envelope, 1,650 verts / 3,296 faces, 578.6 × 624.7 × 671.1 mm.
- **Size:** 164,884 bytes.
  **sha256:** `f5c2c02bd1b7575f4dea9af8233e13bdec715f6b790cba3970e2fa85282d4919`.
- **Role:** automatic fallback if the detailed mesh is absent (`alignment.json` → `asset_basic`).

## ot2/ot2_reference_detailed.step  — CAD source (for future URDF/USD authoring)

- **Source:** same repo, `reference-model/STEP/OT-2 Reference Model Detailed.STEP`.
- **What it is:** the parametric CAD master (a single "Stripped Down MegaModel" PRODUCT containing
  **26 BREP solids** — verified; solids are index/unnamed, so enclosure-vs-deck must be classified
  by geometry, not by part name). Size 3,943,530 bytes.
  **sha256:** `f8bf145b878683337ec0f89b74668bd7e350d674777762fab9befbcd014b42d4`.
- **Role:** higher-fidelity source if we later want per-part meshes (STEP → GLB via `cascadio`,
  split by solid) instead of the single-shell STL.

## ot2/ot2_deck_RevA2.dxf  — deck CAD (cross-check)

- **Source:** same repo, `deck/CNC_DECK_RevA2.DXF`. Size 1,167,094 bytes.
- **Role:** the removable-deck CNC drawing with exact slot geometry — an independent cross-check on
  the deck slot coordinates we already read from `opentrons_shared_data` (see `decks/ot2_standard.json`).

## Usage in the twin

The mesh is a **visual chassis only** (non-colliding). The twin's *functional* geometry — deck slot
offsets and every well coordinate — remains exact, read from the real Opentrons deck + labware
definitions (see `../deck.py`). The mesh adds realism; it never becomes a source of guessed
coordinates.

## Candidate extension assets (real, verified — for later integration)

| Asset | Source | Format | License (verified) | Notes |
|---|---|---|---|---|
| OT-One full robot render | Opentrons Sketchfab (`mitchdunn`/Opentrons) | glTF/GLB/USDZ | **CC-BY 4.0** | 457k tris, free download; the *older* OT-One, not OT-2 — visualization only |
| OT-One hardware | `Opentrons/otone_hardware` | STL + DXF (82 files: 66 STL, 16 DXF) | **Apache-2.0** | legacy single-pipette platform; adapt geometry to OT-2 scale |
| Community labware (tube/tip racks) | `tyhho/OT-2_3D_Designs` | STL + DesignSpark `.rsdoc` | **TAPR OHL** (repo "NOASSERTION") | 0.75/1.5/15/50 mL racks, 300 µL tip-rack — reverse-engineered consumables, not the robot |
| Labware visuals | Opentrons labware definitions | generated from exact dims | (defs) | no mesh needed; the twin builds these from real dimensions |

_Verification note: platform models on Printables/Thingiverse/MyMiniFactory are Cloudflare-blocked to
automated fetch but corroborated by web search (title + author). Full verified inventory + conversion
toolchain in `../../docs/OT2_ASSET_DOSSIER.md`._
