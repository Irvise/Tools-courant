# inp2rad support matrix — I/O, preprocessing, output and post-processing

This document covers only the **input/preprocessing/output** topic.  Material,
load/BC and contact coverage is documented separately in the main README.

Legend:

* **Supported** — recognised by the converter and translated to the listed
  Radioss card or behaviour.
* **Feasible, not implemented** — no format/solver obstacle, simply not coded
  yet; requests in this class are reported as warnings.
* **Not supported (solver/format reason)** — the Abaqus concept has no direct
  Radioss equivalent or cannot be represented by the generated deck; the
  converter warns and leaves the data out.

## 1. Input deck and preprocessing

| Abaqus card / construct | Status | Radioss result / behaviour |
| --- | --- | --- |
| `**` comment lines | Supported | Dropped from the converted deck (comments, not data). |
| Quoted names (`ELSET="part (left)"`) | Supported | Names are normalized internally by `sanitize_inp_line` (quotes removed, `()@\`` replaced with `_`) because the downstream `.inp` readers use restricted character classes.  The original spelling is stored in `display_names` and used in Radioss part/set titles, so `part (left)` appears in the output deck as `part (left)` while internal keys use `part _left_`. |
| `*INCLUDE, INPUT=file` | Supported | File contents merged into one deck. Recursive/quoted includes supported (nesting limited to 20); cycles skipped with warning. |
| `*INCLUDE` with missing file | Supported with warning | Card replaced by `** inp2rad: missing INCLUDE ... - contents ignored`; no literal `*INCLUDE` is left for later stages to ignore silently. |
| `*SYSTEM, ID=n` | Supported | `/TRANSFORM/POSITION/n`; nodes grouped under that transform, `//SUBMODEL` / `//ENDSUB` around the node block. Numeric explicit IDs are preserved (leading zeros normalized: `01` -> `1`); non-numeric, duplicate or missing IDs get a free number with a warning. |
| `*SYSTEM, TYPE=CYLINDRICAL|SPHERICAL` | Supported (coordinate conversion) | Cylindrical `(r, theta, z)` with `theta` the azimuth in the local XY plane from local X; spherical `(r, theta, phi)` with `theta` the same azimuth and `phi` the polar angle from local Z (degrees). Coordinates are converted to global XYZ using the system origin, axis and X reference; an identity `/TRANSFORM/POSITION` frame is written. Warning printed. Curved direction fields (BCs, orthotropy, output skew projection) are not reproduced. |
| `*SYSTEM` other parameters (`NSET=`, ...) | Preserved as metadata | Kept in a `# TYPE=... NSET=...` comment in the transform block. |
| `*SYSTEM` with no coordinate data | Supported with warning | No `/TRANSFORM` written. |
| `*ELSET, ELSET=..., GENERATE` / `*NSET ... GENERATE` | Supported | Expanded to explicit ID lists; missing or non-numeric ranges are warned about and skipped. |
| Circular/nested `*ELSET` references | Supported with warning | Cycle ignored by `resolve_elset` (no recursion error); remaining numeric members are kept. |
| Elements with no ELSET | Supported | Placeholder ELSET created in preprocessing; per-block generated `*ELEMENT` cards inserted in numeric ID order, including at EOF. |
| Consecutive `*ELSET` cards | Supported | No keyword is skipped by the placeholder replacement logic. |
| `*ASSEMBLY` / part-instance decks | Not supported (format reason) | Rejected with `ValueError` so GUI callers receive a `False` status. Flatten the model first. |
| Debug dumps (`debug_mode = True`) | Supported | Intermediate files written next to the input deck (or the current directory when called as a library), via `debug_write`. |

## 2. Engine file and run control

| Abaqus card / construct | Status | Radioss result / behaviour |
| --- | --- | --- |
| `*DYNAMIC, EXPLICIT` / `*DYNAMIC, DIRECT, EXPLICIT` | Supported | `/RUN/<name>/1`, run time, `/DT/NODA/CST/0` initial time step. A missing time line is warned about and defaults are used. |
| `*VARIABLE MASS SCALING, DT=` / `*FIXED MASS SCALING, DT=` | Supported | Overrides the initial time step. |
| `*OUTPUT, FIELD, NUMBER INTERVAL=n` | Supported | Sets `/ANIM/DT` interval and `/TFILE` sampling from `run_time / n`; non-positive `n` is warned about. |
| `*OUTPUT, FIELD, TIME INTERVAL=t` | Supported | Sets `/ANIM/DT` and `/TFILE` intervals. |
| `*OUTPUT, FIELD, VARIABLE=<list>` | Supported | Only `/ANIM` cards matching the requested variables are emitted. Mappings: `U` (`U1..3`, `DISP`) -> `/ANIM/VECT/DISP`; `V`, `A` -> VEL/ACC; `RF` (`RF1..3`) -> `/ANIM/VECT/FREAC`; `S` (`S11..33`, `VONM`) -> brick/shell stress and VONM; `E` (`E11..33`) -> brick/shell strain; `PE`/`PEEQ` -> brick/shell plastic strain; `TEMP` -> nodal + element temperature; `ENER` -> element/brick/shell energy; `DENS`, `STATUS`, `DAMAGE` -> element data; `P`/`CONTACT`/`CPRESS`/`CFORCE` -> contact vectors/pressure. Core `/ANIM/NODA/DT` and `/ANIM/NODA/DMAS` are always written. |
| `*OUTPUT, FIELD, VARIABLE=PRESELECT` (or no variable list) | Supported | Full default `/ANIM` set is written. |
| Unknown field output variable | Supported with warning | Listed in a warning; no matching card is emitted. |
| `*OUTPUT, HISTORY, TIME INTERVAL=n` / `NUMBER INTERVAL=n` | Supported | Updates `/TFILE` sampling interval. A bare interval-only request is not warned about. |
| `*OUTPUT, HISTORY`, `NSET=` / `*NODE PRINT|FILE, NSET=` | Supported | Starter `/TH/NODE` group with variables mapped from the request (`U` -> `D`, `V` -> `V`, `A` -> `A`, `RF` -> `REACX/Y/Z`, `TEMP` -> `TEMP`, coordinates -> `XYZ`); legacy default `DEF REACX REACY REACZ` when no variables are listed. |
| `*OUTPUT, HISTORY`, `ELSET=` / `*ELEMENT PRINT|FILE, ELSET=` | Supported | Starter `/TH/BRIC` (solids), `/TH/SHEL` (quads) or `/TH/SH3N` (trias) groups; variables mapped to BRIC/SHEL groups (`S` -> STRESS, `E` -> STRAIN, `PE`/`PEEQ` -> PLAS, `IE`/`ENER` -> IE/IEM, `STATUS` -> OFF, brick `E13` -> EPSZX). `TEMP` is valid for `/TH/BRIC` only; for shells it is dropped with a warning. |
| `*CONTACT PRINT|FILE` / history requests with `INTERACTION=` | Supported when interface name is known | Starter `/TH/INTER` group mapped to the generated `/INTER/...` ID. Valid Radioss variables/groups are used: `CFORCE`/`CSTRESS`/`P` -> `FN`, `FT`; `FX/FY/FZ` -> `|F|`; explicit `FNX/Y/Z`, `FTX/Y/Z`, `MX/Y/Z`, `|FN|`, `|F|`, `OFRIC`; default `DEF`. Unmatched names remain commented and warned. |
| Requests with an unknown set/interface or unmapped variables | Supported with warning | Kept as comments in the engine file with an explicit warning; no `/TH` group is generated. |
| `/TH/TITLE` | Supported | Always followed by a title line (`Time history for <name>`). |
| Output file naming | Supported | `<prefix>_0000.rad` (starter) and `<prefix>_0001.rad` (engine). `output_dir`/`output_prefix` can be supplied by library/GUI callers. |

Note: the Radioss Starter keyword for solid-element time histories is
`/TH/BRIC` (the Reference Guide and OpenRadioss starter reader use `BRIC`;
`BRICK` is only an informal name).  All `/TH/...` groups are written to the
**starter** deck; the engine deck keeps run control and `/ANIM` cards.
| Radioss version selection | Supported | `radversion` (2023/2025) set via `radv` argument or command-line `--radv`; GUI parameter propagation fixed. |

## 3. Feasible, not implemented (I/O scope)

* Exact projection of cylindrical/spherical `*SYSTEM` directions for boundary
  conditions, orthotropic material axes and TH output skews.  Node positions
  are converted, but the Radioss frame is still Cartesian.
* Generating `/TH` groups for history requests whose target set/interface is
  not defined in the deck (they remain commented and warned).
* Generating print/file cards for request types outside the mapping in
  section 2 (for example `*CONTACT PRINT` with an unrecognised interaction).
* Direct support for `*ASSEMBLY` part-instance decks without flattening.
* Arbitrary output-variable aliases beyond the mapping in section 2.

## 4. Not supported for solver/format reasons (I/O scope)

* Part/instance hierarchies: the generated flat starter has no instance
  concept; the input must be flattened.
* Curved system *directions*: Radioss `/TRANSFORM/POSITION` is a fixed
  Cartesian frame, so a spherical/cylindrical system cannot be reproduced
  exactly for directional data; node coordinates are converted to global XYZ
  and an identity frame is emitted, with a warning.
* Abaqus contact print requests whose interface cannot be matched by name are
  preserved as comments only; Radioss `/TH/INTER` needs a concrete interface ID.
* Nodal temperature time histories for shell elements: `/TH/SHEL` and
  `/TH/SH3N` have no `TEMP` variable, so such request variables are dropped
  with a warning (solid `/TH/BRIC` still supports `TEMP`).

## 5. Explicit "silently ignored" list (now warned)

The following data used to disappear without any message.  Each case now
produces a `### WARNING ###` line (and, for output requests, a comment in the
engine file):

1. Missing `*INCLUDE` targets — contents are not converted.
2. Recursive `*INCLUDE` cycles and includes nested deeper than 20 levels.
3. `*OUTPUT, FIELD` variables with no `/ANIM` equivalent.
4. `*OUTPUT, HISTORY`, `*NODE PRINT`, `*ELEMENT PRINT`, `*CONTACT PRINT` /
   `FILE` requests whose target or variables cannot be mapped (mapped ones
   now produce real starter `/TH` groups).
5. Non-rectangular `*SYSTEM` coordinate conversion and unrecognised `TYPE=`
   values; duplicate or non-numeric explicit system IDs are renumbered with a
   warning (leading zeros are normalized silently).  TH variables without an
   equivalent for their group (e.g. shell `TEMP`) are dropped with a warning.
6. `*SYSTEM` cards without coordinate data or with an unsupported range line.
7. `*ELSET`/`*NSET GENERATE` cards without a numeric start/end/step.
8. Circular `*ELSET` references.
9. `*RIGID BODY` with `ROT NODE` but no `REF NODE`, and BC/CLOAD DOF fields
   that cannot be parsed as integers (`ppm_rigids` leaves those lines intact).
10. `*DYNAMIC` cards whose time data line is missing or malformed.
11. Non-positive `NUMBER INTERVAL` values on output cards.

## 6. Test coverage

Automated coverage consists of the fast I/O/preprocessing/output tests under
`tests/` (no solver required).  They cover includes, preprocessing, system ID
preservation and curved node conversion, field variable -> `/ANIM` mapping,
`/TH` group generation for node/element/contact requests, and an end-to-end
starter/engine write.  All other conversion paths remain untested; the P2 lane
is adding broader coverage in a separate branch.  Treat converter warnings as
the primary safety net and review the generated starter/engine decks before
running them.
