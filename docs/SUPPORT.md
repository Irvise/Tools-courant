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
| `*DAMAGE EVOLUTION, TYPE=DUCTILE` | `/FUNCT` (eps-plastic, damage) | No automatic Radioss failure model mapping; curve must be hooked up manually. |
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

### Warnings and limitations

All ignored material data is reported with a `### WARNING ###` line on stdout.
Temperature/orientation notes for data that is kept are also written as
comments into the generated Radioss deck; data that is skipped entirely is only
reported on stdout. In particular:

* temperature-dependent density and elasticity use the first data row only
  (normally the coldest one);
* D1 compressibility for neo-Hookean and Mooney-Rivlin materials is not mapped;
* orthotropic material directions follow the `.inp` global axes and require a
  material orientation on the Radioss property;
* `*PLASTIC` data with unsupported hardening rules or with extra temperature /
  field columns is skipped rather than converted into meaningless curves;
* `*DAMAGE EVOLUTION` is preserved as a function but is not wired into a
  failure model automatically.

### Tests

Fast unit tests (no solver required):

```sh
python3 -m unittest discover -s input_converters/inp2rad/tests -v
```
