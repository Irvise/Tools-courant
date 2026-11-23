# inp2rad support notes

This file documents the features that inp2rad converts and the data that is
reported as unsupported. Other topic areas are documented elsewhere; this
version covers **materials**.

## Materials

### Material dispatch

Materials are matched by *required-key subset* checks (`check_if_*`): a law is
selected when its **required** keys are present, regardless of any additional
(unsupported) keys. Extra parameters on a material card therefore no longer
cause the whole material to be silently dropped.

Only one main material card is emitted per material ID. The write stage uses a
`claim_material()` guard over checks in priority order (LAW93 orthotropic first,
then LAW1, LAW36, the hyperelastic laws, LAW95, LAW111 and MAT VOID). This
matters for materials that define more than one kind of data: for example, a
material with `*ELASTIC, ENGINEERING CONSTANTS` (all nine constants) **and**
`*PLASTIC` writes only `/MAT/LAW93`; the plastic curve is not emitted as a
second main material. Similarly, an isotropic elastic material with plastic
data writes LAW36, not an additional LAW1. Extra material cards (`/VISC/PRONY`,
`/FAIL/JOHNSON`, `/DAMP`, damage-evolution `/FUNCT`) are additive and are not
affected by this guard.

A material with elastic data but no `*DENSITY` cannot be written; a warning is
issued at the end of material conversion.

### Keyword / law mapping

| Abaqus `.inp` data | Radioss output | Notes |
| --- | --- | --- |
| `*DENSITY` | density on the material card | First row only; temperature column reported as ignored. |
| `*ELASTIC` | `/MAT/ELAST` (LAW1) | `E, nu` first row; temperature columns reported as ignored. |
| `*ELASTIC, ENGINEERING CONSTANTS` (9 values) | `/MAT/LAW93` (ORTH_HILL), Nrate=0 | True orthotropic elastic; material orientation must be set on the Radioss property. The LAW93 yield-parameter card (SigY=1E30, QR1/CR1/QR2/CR2=0) and Hill ratio cards (R11/R22/R12 and R33/R13/R23 = 1.0) are emitted with documented defaults, so the elastic-only material does not yield. |
| `*ELASTIC, ENGINEERING CONSTANTS` (partial) | `/MAT/ELAST` with E1/nu12 | Warning issued; orthotropy is not approximated. |
| `*ELASTIC, TRACTION` | `/MAT/LAW59` | First G value used; differing G1/G2 and temperature reported. |
| `*PLASTIC` (stress, plastic strain) | `/MAT/PLAS_TAB` (LAW36) + `/FUNCT` | Fscale defaults to 1.0; negative values are made positive. |
| `*PLASTIC, HARDENING=JOHNSON COOK/KINEMATIC/COMBINED` | *not converted* | Warning issued; curve skipped instead of being turned into bogus data. |
| `*PLASTIC` with temperature/field columns or `TEMPERATURE DEPENDENT` | *not converted* | Warning issued and curve skipped. |
| `*HYPERELASTIC, NEO HOOKE` | `/MAT/LAW42` | D1 compressibility is reported as dropped. |
| `*HYPERELASTIC, MOONEY-RIVLIN` | `/MAT/LAW42` | D1 compressibility is reported as dropped. |
| `*HYPERELASTIC, OGDEN` (N=1 or N>1) | `/MAT/LAW82` | All mu/alpha/D triplets are written. |
| `*HYPERELASTIC, MARLOW` with `*UNIAXIAL TEST DATA` | `/MAT/LAW111` | |
| `*HYPERELASTIC, POLYNOMIAL` / `REDUCED POLYNOMIAL` | `/MAT/LAW95` (N<=3) | More than 3 terms are not fitted. |
| `*HYPERFOAM` | `/MAT/LAW62` or `/MAT/LAW70` | |
| `*SUPERELASTIC` | `/MAT/LAW71` | |
| `*VISCOELASTIC, TIME=PRONY` | `/VISC/PRONY` | |
| `*DAMAGE INITIATION, CRITERION=JOHNSON COOK` | `/FAIL/JOHNSON` | |
| `*DAMAGE EVOLUTION` (any `TYPE`) | `/FUNCT` (curve) + `/FAIL/TAB1` | The table is written and wired automatically as `fct_IDd` regardless of `TYPE` (the type is only carried as a label); see "Damage evolution to /FAIL/TAB1". |
| `*ORIENTATION, NAME=...` (direction cosines) | `/SKEW/FIX` + property `Vx/Vy/Vz, Iskew` | Used for orthotropic LAW93 materials; see "Material orientation". |
| `*DAMPING` | `/DAMP` + `/GRNOD/MAT` | |
| `*MASS, ELSET=...` | `/ADMAS` | Warns and skips if the node group cannot be resolved (no `/ADMAS/0/0`). |
| `*MASS` without ELSET | `/GRNOD/NODE` + `/ADMAS` | Node group generated from the node/mass rows on the card; each card gets a unique group ID allocated from the shared node-set counter. |
| Rigid elements / `*RIGID BODY` | `/MAT/VOID`, `/RBODY` | |

The LAW93 trailing cards were verified against the Radioss Starter Reference
Guide, `/MAT/LAW93 (ORTH_HILL)` (Altair Help, 2026): the parameter-yield card
(`SigY`, `QR1`, `CR1`, `QR2`, `CR2`) and both Hill-ratio cards (`R11`/`R22`/`R12`
and `R33`/`R13`/`R23`) are listed unconditionally in the block format with
documented defaults (`SigY = 1E30`, all ratios `1.0`); only the curve-input card
is conditional on `Nrate > 0`. inp2rad emits the unconditionally documented
cards explicitly rather than relying on parser defaults.

### Damage evolution to /FAIL/TAB1

`*DAMAGE EVOLUTION` data is no longer left as an orphan `/FUNCT`. **Every**
damage-evolution table is wired, whatever its `TYPE` (the keyword value is kept
only as a label in the deck and warning text; no type is silently dropped).
inp2rad emits a `/FAIL/TAB1/<mat_ID>` card that references the curve through
`fct_IDd`, and a second, distinct function ID is allocated for the failure-strain
table that `/FAIL/TAB1` requires. The curve itself is still written as its own
`/FUNCT`. Because the mapping is approximate, adding the failure model is
announced with an explicit `### WARNING ###` on stdout at write time.

Mapping assumptions (these are approximations, not exact equivalences):

* `fct_IDd` is the original Abaqus damage table. In Radioss this function is
  evaluated at the *accumulated damage variable*, so the table abscissa is
  interpreted as damage and its ordinate as the damage growth rate. The physical
  meaning of the two columns should be checked against the source model.
* `Dcrit` is the largest damage ordinate of the table, clamped to `(0, 1]`;
  no damage value yields the Radioss default of 1.0. `Dadv` (crack-advancement
  threshold) is deliberately set equal to `Dcrit` so crack advancement starts
  at the same accumulated damage as failure; `D` and `n` remain 0.
* `table1_ID` points to a generated constant failure-strain function
  (`eps_f = 1.0`, two points). This keeps a triaxiality-dependent failure law
  from being invented while satisfying the mandatory `table1_ID` field of
  `/FAIL/TAB1`.
* Shell and solid deletion use the Radioss defaults (one layer / one
  integration point); XFEM and element-size regularisation are not enabled.

The field layout follows `hm_cfg_files/config/CFG/radioss2021/FAIL/fail_tab1.cfg`
and was checked with the built OpenCourant starter. Note that the starter marks
`/FAIL/TAB1` as obsolete (warning 3145); the card is still parsed without error.

### Material orientation

For `*ORIENTATION` cards using the direction-cosine form, inp2rad derives a
right-handed local frame (local 1-axis from the first data row, local 2-axis
from the optional second row or a global axis) and writes a `/SKEW/FIX/<id>`
card. Skew IDs come from a **single shared allocator** seeded with the existing
`*SYSTEM` transform IDs; the gravity `*DLOAD` skew uses the same allocator, so
orientation, gravity and transform frames can never receive the same ID (a
duplicate caused the starter to abort with a frame-ID error). For a shell LAW93
material whose section uses `ORIENTATION=<name>`, the Vx/Vy/Vz direction
cosines and `Iskew` are written on the `/PROP/SHELL` card.

Limitations that produce explicit `### WARNING ###` messages:

* `*ORIENTATION` forms based on node/position systems are not converted;
* a `*SOLID SECTION` with an orientation cannot be expressed on the emitted
  `/PROP/SOLID` card (Radioss needs `/PROP/SOL_ORTH`), so the skew is generated
  but the warning states it could not be applied;
* a LAW93 material with no orientation keeps the `.inp` global axes.

### Temperature dependence

The emitted material laws were checked against the bundled Radioss starter
documentation (`hm_cfg_files/config/CFG/.../MAT/*.cfg` and the Fortran readers
under `starter/source/materials/mat/`). None of the laws inp2rad writes —
LAW1 (`/MAT/ELAST`), LAW36 (`/MAT/PLAS_TAB`), LAW93 (`/MAT/LAW93`) or the
hyperelastic laws — has a temperature-dependent field in this Radioss version.
In particular `/MAT/PLAS_TAB` has no `Fct_IDT` temperature curve, and density
and elastic temperature columns cannot be represented. Rather than emitting
silently ignored curves, inp2rad reports explicit `### WARNING ###` messages:
during parsing they name the **source** Abaqus keyword (`*DENSITY`, `*ELASTIC`,
`*PLASTIC`), while at write time they name the **target** Radioss law
(`/MAT/ELAST` LAW1, `/MAT/PLAS_TAB` LAW36, `/MAT/LAW93`) for the data that can
reach a writer. The first (coldest) data row is kept and the dropped rows are
also listed as deck comments. D1 compressibility of the hyperelastic laws is a
parse-time-only warning; those writers have no temperature-data path.

### Warnings and limitations

All ignored material data is reported with a `### WARNING ###` line on stdout.
Temperature/orientation notes for data that is kept are also written as
comments into the generated Radioss deck; data that is skipped entirely is only
reported on stdout. In particular:

* temperature-dependent density, elasticity and plasticity use the first data
  row only (normally the coldest one) and are explicitly reported as unsupported;
* D1 compressibility for neo-Hookean and Mooney-Rivlin materials is not mapped;
* orthotropic material directions follow the `.inp` global axes unless a
  supported `*ORIENTATION` is converted to `/SKEW/FIX`;
* `*PLASTIC` data with unsupported hardening rules or with extra temperature /
  field columns is skipped rather than converted into meaningless curves;
* `*DAMAGE EVOLUTION` is preserved as a function and wired into `/FAIL/TAB1`
  with the documented assumptions above.

### Tests

Fast unit tests (no solver required):

```sh
python3 -m unittest discover -s input_converters/inp2rad/tests -v
```

Solver validation of the LAW93 trailing cards (opt-in):

```sh
INP2RAD_SOLVER_TEST=1 python3 -m unittest discover -s input_converters/inp2rad/tests -v
```

The solver test generates a LAW93 deck with damage evolution and an orientation,
runs the built OpenCourant starter (`-check`) and asserts `0 ERROR(S)`. Set
`OPENCURRENT_STARTER` / `OPENCURRENT_ROOT` to override the default install
paths; the test skips when the starter or its libraries are absent.
