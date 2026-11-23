# inp2rad support notes

## Testing

CI should run the Python test suite (no solver required):

```
python3 -m unittest discover -s input_converters/inp2rad/tests -v
```

The solver-gated load test is skipped by default.  Enable it when the local
OpenCourant build is available:

```
INP2RAD_SOLVER=1 python3 -m unittest tests.test_solver_loads -v
```

It uses `/home/fernando/Build/OpenCourant/OpenCourant/exec/starter_linux64_gf`
(override with `INP2RAD_STARTER`) and the same `RAD_CFG_PATH`/`LD_LIBRARY_PATH`
setup as `openradioss_gui/runopenradioss.py`.

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
  `XX/YY/ZZ` on the same `/CLOAD` card. The card uses the modern Radioss
  layout (`funct, DIR, skew, sensor, grnod, Itypfun, Ascalex, Fscaley`,
  `Itypfun=1`). A solid/shell-only deck has no rotational DOFs and the built
  starter rejects `XX/YY/ZZ` with error 845; inp2rad therefore emits a zero
  velocity `/INIVEL/NODE` card on one loaded node to enable `IRODDL` whenever
  moment loads are present. The validation is covered by the solver-gated test.
* `SYSTEM=<id>` on a boundary/load keyword is written as the card's `skew_ID`.
  Rectangular `*SYSTEM` coordinate data is emitted as `/SKEW/FIX/<id>`.
  `*SYSTEM` header parameters (for example `TYPE`) are discarded during
  preprocessing and a warning is printed.
* An unresolved NSET (or a node set that was never defined) is skipped with a
  warning; cards with a zero group ID are not emitted.
* `/IMPDISP` and `/IMPVEL` use the parsed step time for `Tstart`/`Tstop`.
  When step time cannot be parsed the card keeps `Tstart=0`, `Tstop=1E31`
  and a warning is printed.
* `OP=NEW` ends every earlier load/BC entry of the same keyword family at the
  end of the preceding step; `OP=MOD` is the default and only the entries that
  are explicitly redefined are replaced from their step onward. An entry that
  is never redefined persists until the last step. Each entry's `/FUNCT` is
  gated to zero outside that active window, so a step-2 redefinition does not
  leak into step 1 (and vice versa) on the single Radioss time axis.
* `SCALEX`, `SCALEY`, `SHIFTX` and `SHIFTY` on `*AMPLITUDE` are applied to the
  sampled curve. `TIME=TOTAL TIME` curves stay on the global time axis (no
  step-local restart); the default `TIME=STEP TIME` restarts at each step.

### *AMPLITUDE

TABULAR and EQUALLY SPACED values are passed directly to `/FUNCT`. SMOOTH STEP,
EXPONENTIAL, DECAY, AGGREGATE, PERIODIC (Fourier series) and MODULATED
(`A0 + A*sin(w1*(t-t0))*sin(w2*(t-t0))`) are sampled into piecewise-linear
`/FUNCT` curves; PERIODIC and MODULATED are sampled over the longest parsed
step, or two periods when no step time is available.
`DEFINITION=USER`, `SOLUTION DEPENDENT`, `BUBBLE` and `ACTUATOR` cannot be
expressed as a Radioss `/FUNCT(time)`. They emit an explicit `### WARNING ###`
naming the form and the data that was dropped; USER/BUBBLE/ACTUATOR use the
constant 1.0 fallback and SOLUTION DEPENDENT uses its initial amplitude as a
constant. These are never silent fallbacks. An unknown amplitude name
referenced by a BC/load also warns and uses the constant default; function 1 is
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
* `CENT`, `CENTRIF`, `ROTA`: converted to `/LOAD/CENTRI` with `Dir=YY`. The
  Abaqus magnitude is the angular velocity itself (not omega squared), so it
  is passed through unchanged as `Fscale_y`. A `/FRAME/FIX/<id>` card preserves
  the rotation centre (Abaqus point 1) and axis direction (point 2 - point 1):
  the frame Y axis is the rotation axis and its Z axis is an orthogonal
  vector. `Ivar=2` is used when the referenced amplitude varies in time.
* `HP`, `TRVEC`, `TRSHR` in `*DSLOAD` are approximated as uniform normal
  pressure (`/PLOAD`) and the lost height/shear variation is reported.
* Other pressure/body load types are skipped with a warning.

### *INITIAL CONDITIONS

`TYPE=VELOCITY` and `TYPE=ROTATIONAL VELOCITY` are written as `/INIVEL/TRA`
and `/INIVEL/ROT` respectively. Component lines use `node_or_set, component,
value` with component 1/2/3 mapping to X/Y/Z. Unresolved node sets are
skipped with a warning, and numeric nodes with equal values are grouped.

## Remaining approximations

* Multi-step bodies are flattened onto one Radioss time axis. Step-local time
  origins are re-created per step, but perturbation/buckle/frequency steps,
  `*LOAD CASE` scale-factor combinations, load-case superposition and
  restart/re-start basin semantics are not modelled (warnings are printed).
  DOF ranges (`node, 1, 3`) are tracked by their first DOF only when deciding
  which later definition replaces them.
* `TIME=TOTAL TIME` curves use the original function directly, so the
  step-window gating described above does not apply to them; use Tstart/Tstop
  on imposed conditions where available.
* PERIODIC and MODULATED curves are sampled over a finite horizon (the longest
  step). If a Radioss run extends beyond the last sample, `/FUNCT` holds the
  final ordinate rather than continuing the Fourier series; extend the step
  time or resample the amplitude if that matters.
* `VALUE=ABSOLUTE` amplitudes, solution-dependent dependence, user
  subroutines (UAMP/VUAMP), bubble loading and co-simulation actuators cannot
  be represented by static `/FUNCT` data and are only covered by warnings.
* The rotational-DOF enabler writes zero initial velocities on one loaded node;
  it changes no forces but does add one nodal initial-condition entry.
