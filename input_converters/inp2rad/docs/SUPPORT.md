# inp2rad support notes

## Testing

CI should run the Python test suite (no solver required):

```
python3 -m unittest discover -s input_converters/inp2rad/tests -v
```

## Boundary conditions, loads, amplitudes and initial conditions

The converter aims to fail loudly rather than silently drop data in this area.
Every ignored or approximated item prints a `### WARNING ###` line.

### *BOUNDARY / *CLOAD

* `TYPE=DISPLACEMENT` and `TYPE=VELOCITY` are converted to `/BCS`,
  `/IMPDISP` and `/IMPVEL`. `OP=NEW` clears earlier entries for the same
  node set, and trailing commas on parameters are accepted.
* Predefined conditions: `ENCASTR`/`ENCASTRE`, `PINNED`, `XSYMM`, `YSYMM`,
  `ZSYMM`, `XSIDE`, `YSIDE`, `ZSIDE`, `XSPHERE`, `YSPHERE`, `ZSPHERE`.
* `*CLOAD` DOF 1/2/3 become forces `X/Y/Z`; DOF 4/5/6 become moments
  `XX/YY/ZZ` on the same `/CLOAD` card.
* `SYSTEM=<id>` on a boundary/load keyword is written as the card's `skew_ID`.
  Rectangular `*SYSTEM` coordinate data is emitted as `/SKEW/FIX/<id>`.
  `*SYSTEM` header parameters (for example `TYPE`) are discarded during
  preprocessing and a warning is printed.
* An unresolved NSET (or a node set that was never defined) is skipped with a
  warning; cards with a zero group ID are not emitted.
* `/IMPDISP` and `/IMPVEL` use the parsed step time for `Tstart`/`Tstop`.
  When step time cannot be parsed the card keeps `Tstart=0`, `Tstop=1E31`
  and a warning is printed. Multiple steps are approximated by shifting
  amplitude abscissae by the cumulative step start time.

### *AMPLITUDE

TABULAR and EQUALLY SPACED values are passed directly to `/FUNCT`. SMOOTH STEP,
EXPONENTIAL, DECAY and AGGREGATE are sampled into piecewise-linear `/FUNCT`
curves. Unsupported forms (USER, BUBBLE, PERIODIC, ...) fall back to the
constant default with a warning. An unknown amplitude name referenced by a
BC/load also falls back to the constant default with a warning; function 1 is
never referenced implicitly.

### *DLOAD / *DSLOAD

* `GRAV`: one `/GRAV` plus a non-degenerate `/SKEW/FIX` per entry. The
  reference axis is chosen from the global axis least aligned with gravity.
  Numeric element IDs in `*DLOAD` cannot be mapped to a node group, so the
  load is applied to the whole model with a warning, but other gravity
  entries are still converted.
* `P`, `P1`..`P6`: face pressures become `/PLOAD` on `/SURF/SEG` faces. A
  separate surface is built for each `(element set, face)` pair, so `P1` and
  `P2` on the same elset no longer share a surface.
* `CENT`, `CENTRIF`, `ROTA`: converted to `/LOAD/CENTRI`. Off-axis rotation
  axes snap to the closest global axis with a warning; the centre coordinates
  are not preserved.
* `HP`, `TRVEC`, `TRSHR` in `*DSLOAD` are approximated as uniform normal
  pressure (`/PLOAD`) and the lost height/shear variation is reported.
* Other pressure/body load types are skipped with a warning.

### *INITIAL CONDITIONS

`TYPE=VELOCITY` and `TYPE=ROTATIONAL VELOCITY` are written as `/INIVEL/TRA`
and `/INIVEL/ROT` respectively. Component lines use `node_or_set, component,
value` with component 1/2/3 mapping to X/Y/Z. Unresolved node sets are
skipped with a warning, and numeric nodes with equal values are grouped.
