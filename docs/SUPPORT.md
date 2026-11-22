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

### Known limitations / warnings

| Keyword / setting | Behaviour |
| --- | --- |
| `*CONTACT EXCLUSIONS` | Block is skipped with a warning; excluded pairs are **not** translated.  The converter never prompts for input. |
| Rate/temperature-dependent `*FRICTION` (or `DEPENDENCIES=`) | Only the constant coefficient is used; a warning is emitted. |
| `*COHESIVE BEHAVIOR` / cohesive contact | Traction-separation is dropped with a warning. |
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
`start()` / `write_output()` conversion that mocks interactive prompts).

Run it with:

```
python3 -m unittest discover -s input_converters/inp2rad/tests
```

The tests are **not yet wired into CI** (no workflow changes are part of this
topic), so they must be run manually until a cross-branch CI update lands.
