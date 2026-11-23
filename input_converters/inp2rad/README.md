# INP to Rad converter

## Description

This Python script converts .inp format to Radioss (.rad) format.
It can be used as a standalone tool or as a plugin to the [OpenCourant gui tool](https://github.com/OpenCourant/Tools/tree/main/openradioss_gui).
It is provided “as is”, and should be considered as 'beta' today, but has been successfully tested on a wide range of explicit models and already supports most commonly used element formulations, material laws, loadings and boundary conditions.
Through provision of this tool, we hope to further enhance the accessibility of OpenCourant by enabling the use of open-source pre-processors supporting the .inp format such as [PrePoMax](https://prepomax.fs.um.si).

## Installation

You need to have a python3 installation on Linux or Windows.

* On ***Windows*** : check [python.org](https://www.python.org/) web site to install Python
* On ***Linux***, install python from your OS Repository.

  * On RedHat, CentOS, Rocky Linux

          dnf install python3
          dnf install python3-tkinter

  * On Debian, Ubuntu

          apt-get install python3
          apt install python3-tk

 
 ## Use With OpenCourant Gui if self compiling

 inp2rad is packaged with comiled distributed OpenCourant releases, these steps are needed only when self compiling OpenCourant

 install openradioss_gui from tools

 add inp2rad.py to the openradioss_gui folder in your installation

 
 ## Following only needed for Installation as commandline executable

  install the pyinstaller package

  * On Linux as root

          pip3 install pyinstaller
  
  * On Windows

          pip install pyinstaller

Apply the command:

* On ***Windows*** launch

        install.bat

* On ***Linux*** launch as root

        install.sh

This will install the inp2rad.py into Python library collection and inp2rad[.exe] into execution directory


## Supported .inp keywords and Syntax

The convertor aims to support .inp format with a good degree of flexibility, case, spacing and most special characters should be ok, use of ELSET, NSET names inside other ELSET, NSET is supported

Supported keywords: (not all sub-options necessarily supported):

*AMPLITUDE (only TABULAR, default form)

*BOUNDARY (default, SPC type and TYPE=DISPLACEMENT, TYPE=VELOCITY)

*BOUNDARY condition mappings ENCASTR, PINNED, XSYMM, YSYMM, ZSYMM
    
*CLOAD

*COHESIVE SECTION

*CONTACT

*CONTACT PAIR

*CONTACT PROPERTY ASSIGNMENT

*CONTACT PRINT / *CONTACT FILE (with INTERACTION -> /TH/INTER)

*COUPLING, *DISTRIBUTING or *KINEMATIC

*DAMAGE INITIATION, CRITERION = JOHNSON COOK

*DAMPING,( with ALPHA =, BETA =, for material damping)

*DENSITY

*DISTRIBUTING

*DISTRIBUTING COUPLING

*DLOAD (only GRAV type)

*DSLOAD, (Pressure Load Types P, P1, P2, P3, P4, P5, P6)

*ELEMENT, *TYPE= 
  
         DCOUP3D
       
         CONN3D2, (RIGID or HINGE)

         SPRINGA
  
         S3
         
         S3R
         
         M3D3
  
         R3D3
  
         S4
         
         S4R
         
         R3D4
         
         M3D4R
         
         C3D4
         
         C3D6
         
         COH3D6
         
         SC6R
         
         SC8R
         
         C3D8
         
         C3D8I
  
         COH3D8
         
         C3D8R
         
         C3D10
         
         C3D10M

*ELEMENT PRINT / *ELEMENT FILE (with ELSET -> /TH/BRIC, /TH/SHEL or /TH/SH3N)

*ELSET, ELSET (GENERATE supported)

*FRICTION (with coefficient on next line)

*FRICTION, ROUGH

*HYPERELASTIC (MOONEY-RIVLIN, OGDEN, NEO HOOKE, POLYNOMIAL, REDUCED POLYNOMIAL and MARLOW (only with *UNIAXIAL TEST DATA version) forms only)

*HYPERFOAM, (with either TEST DATA or MU ALPHA PR parameters)

*INCLUDE (include files supported for input, the output .rad file will be a single merged file)

*INITIAL CONDITIONS (VELOCITY only)

*KINEMATIC COUPLING

*MASS

*MATERIAL

*MEMBRANE SECTION

*MPC (generates spring beams)

*NODE

*NODE PRINT / *NODE FILE (with NSET -> /TH/NODE)

*NSET, NSET (GENERATE supported)

*OUTPUT, FIELD / *OUTPUT, HISTORY (variable lists mapped to /ANIM and /TH cards)

*PLASTIC

*RIGID BODY

*SHELL SECTION

*SOLID SECTION

*SUPERELASTIC

*SURFACE, TYPE=ELEMENT or TYPE=NODE

*SURFACE INTERACTION

*SURFACE INTERACTION, NAME=RADIOSS_GENERAL (special usecase to ease PrePoMax usage, existence of this will result in a global general contact)

*SYSTEM

*TIE (TYPE = NODE TO SURFACE or TYPE = SURFACE TO SURFACE)

*UNIAXIAL TEST DATA

*VISCOELASTIC, TIME = PRONY

## Input, preprocessing and output (I/O lane)

The full I/O support matrix, including a list of data that is dropped (with
the warning that now accompanies it), is in
[docs/SUPPORT.md](docs/SUPPORT.md).  Summary:

### Input / preprocessing

* `*INCLUDE, INPUT=...` is expanded before conversion, including quoted paths
  and nested includes.  Include cycles are skipped and missing files are
  reported; the missing card is replaced by a comment so its contents cannot
  be silently ignored.
* Comment lines (`**`) are removed.  Quoted set/part names are normalized
  internally (quotes removed, unsupported characters replaced with `_`) so all
  downstream `.inp` parsers agree on a single name; the original spelling is
  kept as the display name in Radioss part/set titles.
* `*SYSTEM` cards become Radioss `/TRANSFORM/POSITION` blocks.  Numeric
  explicit `ID=` values are preserved (leading zeros normalized, e.g. `01` ->
  `1`); non-numeric, duplicate or missing IDs are assigned a free integer with
  a warning, so hand-written cards and TH groups keep referring to the same
  system.  `TYPE=`, `NSET=` and other parameters are kept as comments.
  Rectangular systems use a rigid frame for local node coordinates.  For
  cylindrical systems `(r, theta, z)` uses `theta` in the local XY plane
  from local X; for spherical systems `(r, theta, phi)` uses `theta` as that
  azimuth and `phi` as the polar angle from local Z.  Those coordinates are
  converted to global XYZ and an identity frame is written (a warning is
  printed).
* `*ELSET`/`*NSET` with `GENERATE` are expanded.  A GENERATE card with no
  numeric range is warned about instead of raising `IndexError`.
* `*ASSEMBLY` (part/instance) decks are rejected with a catchable error; use a
  flattened model.
* Placeholder element blocks created for elements without an ELSET are split
  per referenced ELSET, in deterministic (numeric) element order, including a
  block at end-of-file.  Consecutive ELSET cards are no longer skipped.
* Output files are written next to the input deck by default.  Library and GUI
  callers can pass `output_dir` / `output_prefix` to `start()`,
  `input_read()` or `execute_gui()`; `radv` selects 2023/2025 output.  GUI
  timer/version parameters are now propagated correctly.

### Engine output / post-processing

* A Radioss starter (`*_0000.rad`) and engine file (`*_0001.rad`) are always
  written.  `/TH/TITLE` now includes a title line.
* `*DYNAMIC, EXPLICIT` and `*OUTPUT, FIELD` control run time, animation
  interval and `/TFILE` sampling.  With an explicit field variable list only
  the corresponding `/ANIM` cards are emitted; `VARIABLE=PRESELECT` (or no
  list) keeps the full default set.  The mapping covers displacement,
  velocity, acceleration, reaction force, stress/strain (brick and shell),
  plastic strain, von Mises stress, temperature, density, energy, contact
  force/pressure, damage and element status, including component names such
  as `U1` and `S11`.  Unknown variables are warned about.
* `*OUTPUT, HISTORY, TIME INTERVAL=` updates the time-history sampling.
  `*NODE PRINT/FILE` and node history requests with an `NSET` generate
  `/TH/NODE` groups; `*ELEMENT PRINT/FILE` and element history requests with
  an `ELSET` generate `/TH/BRIC`, `/TH/SHEL` or `/TH/SH3N` groups; contact
  requests whose `INTERACTION=` name matches a generated interface generate
  `/TH/INTER` groups.  These cards are written to the starter deck.  Requests
  with an unresolvable set/interface or variable remain comments in the
  engine deck and produce a warning; variables that have no equivalent for a
  given group (for example `TEMP` on `/TH/SHEL`/`/TH/SH3N`) are dropped with a
  warning.  Contact groups use valid Radioss variables/groups
  (`DEF`, `FN`, `FT`, `|FN|`, `|F|`, `FNX/Y/Z`, `FTX/Y/Z`, `MX/Y/Z`).

### Testing status

Automated coverage in this branch consists of the fast I/O/preprocessing/
output tests in [tests/](tests/) (no solver needed), including field variable
mapping, TH-card generation, curved `*SYSTEM` coordinate conversion and
end-to-end starter/engine checks.  All other conversion paths are untested;
broader coverage is being added by the P2 lane in a separate branch.  Warnings
remain the primary safety net, so review the conversion log before running a
generated deck.
