# Real OT-2 3D Assets — Verified Inventory & Conversion Plan

**Purpose.** Everything real and reusable for the OT-2 digital twin — the official CAD, the
subcomponents, community models, and the exact toolchain to convert them into our two backends
(Isaac Sim 5.1 / USD and MuJoCo / MJCF). This underpins the "real lab, real scientific paper,
nothing guessed" bar: every functional coordinate in the twin is from a real Opentrons definition,
and every 3D asset here is sourced, license-checked, and byte-verified.

**Verification.** Produced by a multi-agent sweep (4 inventory tracks → adversarial verification of
each URL/format/license/size against the live GitHub API + WebFetch), 2026-08-06. Every asset URL
with a download link was confirmed to resolve at the exact byte size claimed; local files were
independently re-hashed and re-measured. Verdicts below are the *verified* ones — not assumptions.

---

## ⚠ License correction (load-bearing — was wrong in the original premise)

The project premise assumed the OT-2 CAD is **Apache-2.0**. **REFUTED by verification:**
`Opentrons/ot2` has **no LICENSE file** — GitHub's `/license` API returns 404 and the repo's
`license` field is `null`. So the OT-2 reference CAD is **UNSPECIFIED / all-rights-reserved by
default**, mitigated only by the repo README's explicit grant that Opentrons provides these files
"for our community to modify their OT-2 robots however they choose." For a **research digital twin +
paper**, that README grant covers us; but **do not claim an OSI license** for these files, and
budget for a written-permission ask from Opentrons if the physical-lab build ever redistributes CAD.
The *separate* `Opentrons/otone_hardware` repo (the older OT-One) **is** genuinely Apache-2.0.

---

## 1. Official Opentrons CAD (`Opentrons/ot2`, branch `master`) — byte-verified

| Asset | Path | Format | Size (bytes) | License | Completeness |
|---|---|---|---|---|---|
| **Reference Model Detailed** ★ | `reference-model/STL/OT-2 Reference Model Detailed.STL` | STL | 2,108,684 | unspecified (README grant) | **full robot**: enclosure, X-gantry, Z carriage + pipettes, deck plate w/ slot grid — 42,172 tris |
| Reference Model Detailed (CAD) | `reference-model/STEP/OT-2 Reference Model Detailed.STEP` | STEP | 3,943,530 | " | parametric master; single PRODUCT w/ **26 BREP solids** (unnamed) |
| Reference Model Basic | `reference-model/STL/OT-2 Reference Model Basic.STL` | STL | 164,884 | " | coarse full-robot envelope, 1,650 verts |
| Reference Model Basic (CAD) | `reference-model/STEP/OT-2 Reference Model Basic.STEP` | STEP | 407,446 | " | coarse envelope CAD |
| **Deck CNC drawing** | `deck/CNC_DECK_RevA2.DXF` | DXF | 1,167,094 | " | exact removable-deck slot geometry |
| Window drawings ×5 | `windows/*.DXF` | DXF | ~112–133k ea | " | front/top/side/rear acrylic cut CAD |

★ = the asset now wired into both twin backends (glass shell). Detailed.STL independently
re-measured: **42,172 triangles, AABB 624.3 × 662.0 × 567.5 mm** — matches Opentrons' published
external size (66 × 57 × 63 cm incl. door/handles).

**Companion data (all verified against `opentrons_shared_data`):** 154 labware v2 definitions,
deck schemas v3/4/5, 11 module v3 definitions (Temperature/Heater-Shaker/Thermocycler/Magnetic
GEN2, etc.). This is where the twin already reads its exact well/slot geometry.

## 2. What's inside the Detailed model (subcomponents)

The Detailed STL/STEP resolves to a single shell whose geometry contains, top→bottom: the **outer
enclosure** (frame + rounded corner posts + front/side/top/rear windows), the **X-gantry rail**, the
**Z-axis pipette carriage** with **pipette bodies**, and the **deck plate** with its **slot grid**.
The STEP holds **26 BREP solids** — the split is geometrically possible but the solids are
index/unnamed, so enclosure-vs-deck-vs-gantry must be classified by geometry (bounding box / Z-band),
not by part name. (Two internal-geometry claims — "18 connected shells", a named-solid tree — could
not be verified without CAD inspection and are left open.)

## 3. Community / third-party assets — verified

| Asset | Source | Format | License (verified) | Trust |
|---|---|---|---|---|
| OT-One full robot | Opentrons **Sketchfab** (`mitchdunn`/Opentrons) | glTF / GLB / USDZ | **CC-BY 4.0** | high; 457k tris, free DL — but it's the *older* OT-One, viz only |
| OT-One hardware | `Opentrons/otone_hardware` | STL + DXF (82 files: 66 STL, 16 DXF) | **Apache-2.0** | high; legacy single-pipette platform, adapt to OT-2 scale |
| Labware racks (tube/tip) | `tyhho/OT-2_3D_Designs` | STL + DesignSpark `.rsdoc` | **TAPR OHL** (repo "NOASSERTION") | high; 0.75/1.5/15/50 mL racks + 300 µL tip-rack, reverse-engineered consumables |
| Misc labware prints | Printables / Thingiverse / MyMiniFactory | STL | mixed CC | med; Cloudflare-blocked to auto-fetch, titles+authors corroborated by search |

No fabricated URLs; every download link that could be opened resolved. Platform-model pages
(Printables etc.) block automated fetch but were cross-checked by web search.

## 4. Conversion toolchain — into our two backends

**The single recommended path per backend** (verified installable on the relevant OS):

**→ MuJoCo (MJCF), macOS arm64 — what we use now.** STL is loaded directly as a `<mesh>` and rendered
as a non-colliding visual (glass) geom; no conversion needed. `mujoco` 3.11 ships cp314 + mac-arm64
wheels. If a *collision* mesh is ever needed (ours is visual-only), decompose with `obj2mjcf` +
`coacd`/VHACD — **caveat: `coacd` ships only cp39 wheels**, so that one step needs Python 3.9 or an
sdist build (`trimesh`/`obj2mjcf` are pure-Python and install anywhere).

**→ Isaac Sim 5.1 (USD), Linux/A6000 — the photoreal backend.** Two options:
- **Direct mesh build (what we use):** read the binary STL and author a `UsdGeom.Mesh` in the stage
  with a `UsdPreviewSurface` **glass material** (opacity ~0.1) — RTX renders `displayOpacity` as
  near-solid, so a real material is required. Fast, no external tool.
- **Per-part split (higher fidelity, future):** `cascadio` converts STEP→GLB preserving the 26
  solids as separate nodes → import GLB natively into USD → classify enclosure/deck/gantry by
  geometry and give each its own material. `cascadio` + `usd-core` both ship cp314 wheels (verified).
  Isaac's own STEP/URDF importer merges everything into one mesh, so `cascadio` is preferred when you
  want the parts separable.

*(Isaac cannot run on macOS — Linux + RTX GPU only; confirmed. glTF import into USD is native.)*

## 5. Alignment (how the mesh seats on the functional deck)

Derived analytically, **not guessed** (see `twin/assets/ot2/alignment.json`): the deck plate is the
dominant up-facing plane in the mesh at local z=338.9 mm, footprint center (312.1, 465.7); the
translate maps it onto the Opentrons functional deck (center 196.5, 178.75, surface z=0) →
`pos = [-115.6, -286.9, -338.9]`. The mesh is a **non-colliding glass shell**; all functional
geometry (slots, wells, collisions, reach) stays exact from the Opentrons definitions.

## 6. Prioritized plan to make the twin look like a real OT-2 — status

| # | Step | Status |
|---|---|---|
| 1 | Pull the **Detailed** STL (not Basic) | ✅ done (42k tris, byte-verified) |
| 2 | Analytic deck-frame alignment | ✅ done |
| 3 | Wire detailed mesh into **MuJoCo** as glass shell | ✅ done (`--chassis`) |
| 4 | Wire detailed mesh into **Isaac** + real **glass material** | ✅ done (UsdPreviewSurface opacity) |
| 5 | **Smooth interpolated motion** in Isaac (fix teleport) | ✅ done (~1 frame/waypoint → ~240–500 interp frames) |
| 6 | Camera clear of the near glass wall; RTX exposure sane | ✅ done |
| 7 | Per-part materials via STEP→GLB (`cascadio`) | ○ future (higher fidelity) |
| 8 | Chemistry-gate overlay in Isaac (MuJoCo has it) | ○ future (BasicWriter is raw RGB) |

## 7. Caveats / open items

- OT-2 CAD license is **unspecified** — README community grant only (see §top). ⚠
- STEP internal named-part tree unverified (needs CAD inspection); 26 solids confirmed, names not. ⚠
- `coacd` cp39-only wheel blocks a pure-3.11 collision-decomposition path (visual path unaffected).
- Community platform pages (Printables/Thingiverse) unverifiable by auto-fetch; corroborated by search.

_Sources: `Opentrons/ot2`, `Opentrons/otone_hardware`, `tyhho/OT-2_3D_Designs`, Opentrons Sketchfab,
`opentrons_shared_data`; PyPI for toolchain wheels. Cross-refs: `twin/assets/PROVENANCE.md`,
`docs/SIMULATION_GUIDE.md`, `docs/LAB_ECOSYSTEM_DUE_DILIGENCE.md`._
