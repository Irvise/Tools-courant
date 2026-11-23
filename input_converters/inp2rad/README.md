# INP to Rad converter

## Description

This Python script converts .inp format to Radioss (.rad) format.
It can be used as a standalone tool or as a plugin to the [OpenCourant gui tool](https://github.com/OpenCourant/Tools/tree/main/openradioss_gui).
It is provided “as is”, and should be considered as 'beta' today, but has been successfully tested on a wide range of explicit models and already supports most commonly used element formulations, material laws, loadings and boundary conditions.
Through provision of this tool, we hope to further enhance the accessibility of OpenCourant by enabling the use of open-source pre-processors supporting the .inp format such as [PrePoMax](https://prepomax.fs.um.si).

## Shared function IDs (`/FUNCT`)

The `/FUNCT` producers migrated on this branch share one process-wide
`FunctionIdAllocator` (defined in `inp2rad.py`): material curves (plasticity and
hyperelastic/uniaxial test data), amplitude curves from `*AMPLITUDE` (created by
`read_amplitudes`, written by `write_functions`), and the inline constants
emitted for gravity (`convert_dloads`) and pressure (`convert_pload`) loads.
Each of these calls `allocate()`, so a deck containing both material curves and
load amplitudes cannot generate duplicate `/FUNCT` IDs. Missing/unknown
amplitudes resolve through `ensure_default_function()` to a single generated
default function shared by boundary, gravity and pressure loads; no load card
falls back to hard-coded ID 1, which may belong to a material curve. Loads with
*no* amplitude still emit their legacy inline constant curve for backward
compatibility. **Other topic branches are not migrated yet — see the
integration note below.**

`get_function_id_allocator()` returns the shared instance. It is reset at the
start of every `main_conversion_sp()` call, so consecutive conversions in the
same Python process (for example from the GUI or from tests) start numbering
again at 1. `reset()` can also be called directly. Legacy call sites may still
pass an explicit `fct_id`; it is only observed as a lower bound and never
rewinds the allocator, so old-style callers cannot reintroduce collisions.
Generated IDs keep their previous numbering: curves are allocated first (in
material parsing order), then amplitudes, then inline load constants.

Regression tests live in `tests/test_function_ids.py` and can be run with:

    python3 -m unittest discover -s input_converters/inp2rad/tests -v

### INTEGRATION NOTE — call sites to migrate when merging other branches

This branch deliberately does not change producers introduced by other topic
branches. When merging them, migrate these exact call sites:

* **p0 — damage/TAB1 IDs:** any new material curve writer that assigns
  `fct_id` / `function_id` / `funct_id` or emits `/FUNCT` (damage evolution
  curves, TAB1-style law IDs and their `write_*` helpers). In
  `convert_materials()` replace local counters or IDs derived from `len(...)`
  with `function_id_allocator.allocate()`, store the returned ID in the
  material dictionary, and pass the allocator in from `main_conversion_sp()`
  (the `allocator=` parameter already exists). Do not reserve IDs by
  incrementing unrelated counters such as `nset_counter` or `material_id`.
* **p1 — `resolve_function_id`:** the resolver that maps an amplitude name to
  an ID must use the shared entries: look up known names in `functs_dict` and,
  for unknown/missing names, call `ensure_default_function(functs_dict,
  allocator)` instead of returning `1` or allocating an ad-hoc curve. It must
  accept the same `allocator` object and preserve `observe(fct_id)` semantics
  for legacy callers. Update every resolver consumer: `convert_boundary()`
  (CLOAD/IMPDISP/IMPVEL), `convert_dloads()` (/GRAV), `convert_pload()`
  (/PLOAD) and `write_functions()` if it starts synthesising cards.
* After each merge, re-run the regression tests (also with `python3 -O`) and
  add a deck exercising the newly migrated producer together with a plastic
  curve and an amplitude so uniqueness and cross-references stay covered.

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

*NSET, NSET (GENERATE supported)

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
