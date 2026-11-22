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
| `*SYSTEM, ID=n` | Supported | `/TRANSFORM/POSITION/n`; nodes grouped under that transform, `//SUBMODEL` / `//ENDSUB` around the node block. |
| `*SYSTEM, TYPE=CYLINDRICAL|SPHERICAL` | Supported (approximation) | Converted to a fixed `/TRANSFORM/POSITION` frame at the reference point; local directions away from that point are not reproduced. Warning printed. |
| `*SYSTEM` other parameters (`NSET=`, ...) | Preserved as metadata | Kept in a `# TYPE=... NSET=...` comment in the transform block; IDs are renumbered sequentially. |
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
| `*OUTPUT, FIELD, VARIABLE=<list>` | Supported | Only `/ANIM` cards matching the requested variables are emitted: `U` -> DISP, `V` -> VEL, `A` -> ACC, `S`/`VONM` -> stress/VONM, `E`/`PE` -> EPSP (solid+shell), `ENER` -> ENER, `P`/`CONTACT` -> contact vectors. Core `/ANIM/NODA/DT` and `/ANIM/NODA/DMAS` are always written. |
| `*OUTPUT, FIELD, VARIABLE=PRESELECT` (or no variable list) | Supported | Full default `/ANIM` set is written. |
| Unknown field output variable | Feasible, not implemented | Listed in a warning; no matching card is emitted. |
| `*OUTPUT, HISTORY, TIME INTERVAL=n` / `NUMBER INTERVAL=n` | Supported (partial) | Updates `/TFILE` sampling interval only. |
| `*OUTPUT, HISTORY` variables | Feasible, not implemented | Recorded as comments in the engine file and warned about; no `/TH/...` cards generated. |
| `*NODE PRINT`, `*ELEMENT PRINT`, `*CONTACT PRINT` (and `FILE` variants) | Feasible, not implemented | Recorded as comments and warned about; no print/file cards generated. |
| `/TH/TITLE` | Supported | Always followed by a title line (`Time history for <name>`). |
| Output file naming | Supported | `<prefix>_0000.rad` (starter) and `<prefix>_0001.rad` (engine). `output_dir`/`output_prefix` can be supplied by library/GUI callers. |
| Radioss version selection | Supported | `radversion` (2023/2025) set via `radv` argument or command-line `--radv`; GUI parameter propagation fixed. |

## 3. Feasible, not implemented (I/O scope)

* Generating `/TH/...` time-history cards from `*OUTPUT, HISTORY` and node/element
  sets (today only the sampling interval is translated, requests are commented).
* Generating Radioss print/file cards from `*NODE PRINT`, `*ELEMENT PRINT` and
  `*CONTACT PRINT`.
* Exact projection of cylindrical/spherical `*SYSTEM` directions onto a Radioss
  transform for nodes far from the system reference point.
* Direct support for `*ASSEMBLY` part-instance decks without flattening.
* Arbitrary output-variable aliases beyond the mapping in section 2.

## 4. Not supported for solver/format reasons (I/O scope)

* Part/instance hierarchies: the generated flat starter has no instance
  concept; the input must be flattened.
* Non-rectangular system frames: Radioss `/TRANSFORM/POSITION` is a fixed
  Cartesian frame, so a spherical system cannot be reproduced exactly — the
  converter emits the best-fit frame at the reference point and warns.
* Abaqus history/contact print requests have no automatic equivalent in the
  generated engine deck; they are preserved as comments only.

## 5. Explicit "silently ignored" list (now warned)

The following data used to disappear without any message.  Each case now
produces a `### WARNING ###` line (and, for output requests, a comment in the
engine file):

1. Missing `*INCLUDE` targets — contents are not converted.
2. Recursive `*INCLUDE` cycles and includes nested deeper than 20 levels.
3. `*OUTPUT, FIELD` variables with no `/ANIM` equivalent.
4. `*OUTPUT, HISTORY`, `*NODE PRINT`, `*ELEMENT PRINT`, `*CONTACT PRINT` /
   `FILE` requests (only sampled interval/ comments are produced).
5. Non-rectangular `*SYSTEM` approximation and unrecognised `TYPE=` values.
6. `*SYSTEM` cards without coordinate data or with an unsupported range line.
7. `*ELSET`/`*NSET GENERATE` cards without a numeric start/end/step.
8. Circular `*ELSET` references.
9. `*RIGID BODY` with `ROT NODE` but no `REF NODE`, and BC/CLOAD DOF fields
   that cannot be parsed as integers (`ppm_rigids` leaves those lines intact).
10. `*DYNAMIC` cards whose time data line is missing or malformed.
11. Non-positive `NUMBER INTERVAL` values on output cards.

## 6. Test coverage

At the time of writing, automated coverage consists of the element tests plus
the fast I/O/preprocessing/output tests under `tests/` (no solver required).
All other conversion paths remain untested; the P2 lane is adding broader
coverage in a separate branch.  Treat converter warnings as the primary safety
net and review the generated starter/engine decks before running them.
