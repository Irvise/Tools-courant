# inp2rad support notes

This document records how the converter maps `.inp` keywords to Radioss cards
for the **contacts / ties / constraints** topic, including limitations and the
warnings emitted when a setting cannot be translated.  For the full keyword
list see [`input_converters/inp2rad/README.md`](../input_converters/inp2rad/README.md).

## Contacts and surfaces

### Element surfaces (`*SURFACE, TYPE=ELEMENT`)

| `.inp` form | Radioss output |
| --- | --- |
| `element_id, face` | `/SURF/SEG/<id>` with the segment nodes |
| `elset_name, face` | `/SURF/SEG/<id>` built from every element in the ELSET |
| blank element/side | `/SURF/PART/EXT/<id>` covering all parts |

* Shell faces may be written as `spos`/`sneg` or as the numeric ids `1`/`2`
  (mapped to `spos`/`sneg`).  Solid faces `1`..`6` map to `s1`..`s6`.
* In addition to C3D4/6/8/10, S3/S4/R3D3/R3D4/M3D3/M3D4R, degraded 6- and
  8-node shells (`S6`, `S6R`, `S8`, `S8R`) and line/beam elements (`S2`,
  `S2R`, `B31`, `B32`, `B33`) produce two-sided segments.  For shells both
  faces use the same **corner** loop with opposite orientation: `spos` is the
  corner loop, `sneg` its reverse (`[2,1,0]` for S6, `[3,2,1,0]` for S8).  The
  extra S6/S8 nodes are mid-side nodes and are not the opposite face.
* These element types are now parsed (they used to be dropped as "unknown"),
  and S6/S8 are written structurally as **degraded** Radioss elements:
  `/SH3N` (corner triangle) and `/SHELL` (corner quad).  The starter accepts
  their `/SURF/SEG` contact faces (validated by the solver-gated tests).
* **2-D/beam faces are not valid 3-D `/SURF/SEG` contact surfaces.**  Radioss
  reads four node ids per segment; a two-node line/beam face makes it read
  node id 0 and abort (`UNDEFINED NODE NUMBER` / null-area errors).  Such
  segments are therefore omitted, warned about, and a surface made only of
  them is withheld from contact/tie lookups (its `*CONTACT PAIR` is skipped).
  Line/beam elements are not emitted as Radioss structural elements because
  inp2rad cannot derive a `/PROP/TYPE3` beam property from the `.inp` deck.
  Use a shell/brick surface, or model beam contact with a Type11 edge
  interface and `/LINE/SURF` manually.
* A surface with a blank side creates exactly one `/SURF/PART/EXT` card using
  the id registered in the surface lookup table.  The part list is rebuilt
  for each surface, so parts from one surface never leak into another.
* Property/group names are matched both by their key and by their
  `collecting_elset_name`, so grouped sections can be referenced by either
  name.

### Node surfaces (`*SURFACE, TYPE=NODE`)

Node-based surfaces are kept in the deck but are deliberately **not**
registered in the surface-id lookup table: their ids are node-group
(`/GRNOD/NODE`) ids, not `/SURF` ids, and emitting them as `Surf_IDm` or as a
`/PLOAD` `surf_ID` would be invalid.  The `<name>___originalnodeset` alias is
created in `nsets` and is what node-to-surface ties resolve; a warning is
emitted that this is an approximation of a true node surface.  A `*CONTACT
PAIR` or `*DSLOAD` that references a node-based surface is skipped with an
"unknown surface" / "element set not found" warning — use an element surface
for contacts and pressure loads.

### Contact interfaces

* `*CONTACT` produces one global self-contact `/INTER/TYPE24` backed by a
  `/SURF/PART/EXT` surface over all structural parts (springs, lumped masses
  and void properties are excluded).
* `*SURFACE INTERACTION, NAME=RADIOSS_GENERAL` (PrePoMax convention) produces
  the same general contact using the `RADIOSS_GENERAL` friction coefficient.
* `*CONTACT PAIR, INTERACTION=<name>` produces one `/INTER/TYPE24` per pair.
  Friction is written together with the interface, so consecutive pairs each
  keep their own coefficient.  Missing or unknown surfaces and malformed
  lines are warned and skipped instead of stalling the conversion.
* `*CONTACT PROPERTY ASSIGNMENT` supplies the friction interaction for a
  general contact.
* `*CONTACT CONTROLS` options `STIFFNESS=` / `GAP=` (`STFAC`, `GAP_MAX` are
  also accepted) set the Type24 `Stfac` and `Gap_max_s`/`Gap_max_m` values.

### Rough / no-slip contact (`*FRICTION, ROUGH`)

Abaqus `ROUGH` contact means *no sliding* once contact is established
(infinite friction).  Radioss **has no equivalent flag**: `/INTER/TYPE24`
(and `/FRICTION`) only offers `Ifric = 0` (static Coulomb), `1` (generalized
viscous), `2` (modified Darmstad), `3` (Renard) and `4` (exponential decay),
and none of these is a no-slip/rough law.  This was checked against the
Radioss 2026 Reference Guide and the starter source
(`starter/source/interfaces/int24/hm_read_inter_type24.F`).

inp2rad therefore:

1. keeps ROUGH interactions distinct from numeric coefficients
   (`ROUGH_FRICTION_MARKER`) instead of silently writing `mu = 1.0`;
2. writes a **large static-Coulomb coefficient** (`ROUGH_FRICTION_COEFF`,
   `1e6`) with `Ifric = 0` as an explicitly documented approximation;
3. adds a `# NOTE: ROUGH contact approximated ...` comment to the deck and
   prints a warning naming the missing no-slip flag and suggesting a tied
   interface for true no-slip contact.

The high coefficient can make a penalty contact stiff; review the interface
(and consider `/INTER/TYPE2` ties for genuine sticking) before production
use.  A solver-gated test confirms the resulting deck is accepted by the
starter.

### Rate/temperature-dependent friction and cohesive contact

* `*FRICTION` / `*SURFACE INTERACTION` with `DEPENDENCIES`, rate or
  temperature options: only the constant coefficient is written to Type24
  `Fric`.  `Ifric` can express a few *velocity*-dependent laws (Darmstad,
  Renard, exponential decay) via `C1..C6`, but there is no way to map an
  arbitrary Abaqus friction table, and **no temperature dependence** exists
  in Type24.  The dependency table is dropped with an explicit warning.
* `*COHESIVE BEHAVIOR` / cohesive contact: Type24 has no traction-separation
  fields, so cohesive contact is dropped with a warning.  Model the adhesive
  layer with cohesive elements/laws instead.

### Known limitations / warnings

| Keyword / setting | Behaviour |
| --- | --- |
| `*CONTACT EXCLUSIONS` | Block is skipped with a warning; excluded pairs are **not** translated.  The converter never prompts for input. |
| `*FRICTION, ROUGH` | No true no-slip flag exists in `/INTER/TYPE24`; a high Coulomb coefficient (`1e6`, `Ifric=0`) is written with a warning and a deck comment instead of the old silent `mu=1.0`. |
| Rate/temperature-dependent `*FRICTION` (or `DEPENDENCIES=`) | Only the constant coefficient is used; the dependency table is dropped with an explicit warning (no temperature dependence in Type24). |
| `*COHESIVE BEHAVIOR` / cohesive contact | Traction-separation is dropped with a warning; use cohesive elements/laws. |
| 2-D/beam element surfaces (`S2`, `S2R`, `B31`, `B32`, `B33`) | Two-node faces are omitted from 3-D `/SURF/SEG` with a warning; the surface is withheld from contact/tie lookups. Line/beam structural elements are not emitted (no beam property mapping). |
| Non-numeric friction coefficient | Falls back to `0.0` with a warning. |
| Unsupported `*CONTACT CONTROLS` options | Warned and dropped. |

## Ties (`*TIE`)

* `TYPE=NODE TO SURFACE` and `TYPE=SURFACE TO SURFACE` map to `/INTER/TYPE2`.
  The default type is `NODE TO SURFACE`.
* `POSITION TOLERANCE=` is written as the tie search distance (`dSearch`).
* The node side resolves, in order, `<name>___nodes`,
  `<name>___originalnodeset`, and the raw NSET name.  The main side also
  accepts node-surface aliases; doing so emits a warning.
* Malformed or unresolved ties are warned and skipped.  Each tie resets its
  name/type/tolerance, so state from a previous tie is never reused.
* With `radversion = 2023`, surface-to-surface ties emit a second symmetric
  interface; with 2025 a single `/INTER/TYPE2` is emitted.

## Couplings

* `*COUPLING` + `*DISTRIBUTING` (and `*DISTRIBUTING COUPLING` on a DCOUP3D
  element) are converted into `*DISCOUP` blocks and then `/RBE3` cards.  A
  coupling is converted using **its own** `REF NODE`, even when no DCOUP3D
  element appears in the deck.
* `*KINEMATIC COUPLING` uses the `NODES_FOR_KC_WITH_REF_NODE_<n>` NSET that
  the converter generates from the coupling's data lines and emits an
  `/RBODY`.  Unknown node sets and malformed weight lines are warned/skipped.

## Rigid bodies (`*RIGID BODY`)

* `*RIGID BODY` by `ELSET=` (a property/part), by a rigid ELSET, or by
  `NSET=` produces `/RBODY` plus the appropriate `/GRNOD/PART` or
  `/GRNOD/NODE` groups.  `DENSITY=` and an optional thickness line are
  honoured.
* Definitions with neither `ELSET=` nor `NSET=`, or without `REF NODE=`, are
  warned and skipped rather than aborting the conversion.
* PrePoMax `ROT NODE` definitions are rewritten to `REF NODE` with the
  rotational DOFs offset by three before conversion.

## MPC constraints (`*MPC`)

| `.inp` type | Radioss output |
| --- | --- |
| `TIE` | `/PART`, `/PROP/TYPE13` and `/SPRING` connection beams |
| `BEAM` | `/RBODY` rigid link |
| `HINGE`, `PIN` | `/RBODY` rigid link with a warning that rotational releases are not preserved |
| anything else | Warned and dropped |

Spring stiffness and mass are calibrated from the largest material modulus and
density in the deck.  If no material is present, the fallback values
(`E = 10.0`, `rho = 1e-9`) are used and a warning is emitted so the
`/PROP/TYPE13` values can be checked manually.  Malformed `*MPC` lines are
warned and skipped.

## Testing

The `unittest` suite under `input_converters/inp2rad/tests/` covers the
contact/tie/constraint conversion paths (including a fast end-to-end
`start()` / `write_output()` conversion that mocks interactive prompts), plus:

* `test_contacts.py`: fast unit tests for rough-contact detection/warnings,
  rate/temperature and cohesive warnings, degraded-shell/line/beam segments,
  and withholding of invalid two-node surfaces.
* `test_solver_surfaces.py`: end-to-end conversion followed by a real
  **OpenCourant starter** run for degraded S6/S8 shell contact faces, two-D/
  beam faces (verifying they are withheld with a warning) and a rough-contact
  deck.  These tests are skipped automatically when the solver is absent.

Run it with:

```
python3 -m unittest discover -s input_converters/inp2rad/tests
```

The solver-gated tests use the starter at
`/home/fernando/Build/OpenCourant/OpenCourant/exec/starter_linux64_gf` with
`RAD_CFG_PATH`/`LD_LIBRARY_PATH` derived from `OPENCOURANT_PATH` (both
overridable via `INP2RAD_STARTER` / `OPENCOURANT_PATH`).  They skip when the
binary or config tree is missing, so the suite stays fast on machines without
a solver build.

The tests are **not yet wired into CI** (no workflow changes are part of this
topic), so they must be run manually until a cross-branch CI update lands.
