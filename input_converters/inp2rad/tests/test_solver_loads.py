"""Solver-gated validation of moment loads and /LOAD/CENTRI.

These tests are skipped unless ``INP2RAD_SOLVER=1`` is set in the environment.
They run the locally built OpenCourant starter on a tiny generated deck and
check that the starter accepts the emitted BC/load cards.  This catches format
and direction errors that pure text assertions cannot (for example the missing
rotational DOF error produced by a moment /CLOAD on a solid-only model).
"""

import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import inp2rad.inp2rad as converter  # noqa: E402

STARTER = ('/home/fernando/Build/OpenCourant/OpenCourant/exec/starter_linux64_gf')
OPENRADIOSS_ROOT = os.path.dirname(os.path.dirname(STARTER))

DECK = """*HEADING
inp2rad solver load regression deck
*NODE
1, 0., 0., 0.
2, 1., 0., 0.
3, 0., 1., 0.
4, 0., 0., 1.
5, 1., 1., 1.
*NSET, NSET=FIX
1, 2
*NSET, NSET=MOVE
3, 4
*ELEMENT, TYPE=C3D4, ELSET=SOLIDS
1, 1, 2, 3, 4
2, 2, 3, 4, 5
*ELSET, ELSET=SOLIDS
1, 2
*MATERIAL, NAME=STEEL
*DENSITY
7.8e-9
*ELASTIC
210000., 0.3
*SOLID SECTION, ELSET=SOLIDS, MATERIAL=STEEL
*STEP
*STATIC
1.0, 1., 1.
*BOUNDARY
FIX, 1, 3
*CLOAD
MOVE, 1, 10.0
MOVE, 4, 100.0
*DLOAD
SOLIDS, CENTRIF, 100.0, 1., 0., 0., 1., 0., 1.
*END STEP
"""


def solver_environment():
    """Mirror the environment used by openradioss_gui/runopenradioss.py."""
    env = os.environ.copy()
    env.update({
        'OPENRADIOSS_PATH': OPENRADIOSS_ROOT,
        'RAD_CFG_PATH': os.path.join(OPENRADIOSS_ROOT, 'hm_cfg_files'),
        'RAD_H3D_PATH': os.path.join(OPENRADIOSS_ROOT, 'extlib', 'h3d', 'lib', 'linux64'),
        'OMP_NUM_THREADS': '1',
    })
    ld_paths = [
        os.path.join(OPENRADIOSS_ROOT, 'extlib', 'h3d', 'lib', 'linux64'),
        os.path.join(OPENRADIOSS_ROOT, 'extlib', 'hm_reader', 'linux64'),
    ]
    if env.get('LD_LIBRARY_PATH'):
        ld_paths.append(env['LD_LIBRARY_PATH'])
    env['LD_LIBRARY_PATH'] = os.pathsep.join(ld_paths)
    return env


@unittest.skipUnless(os.environ.get('INP2RAD_SOLVER'), 'set INP2RAD_SOLVER=1 to run solver tests')
class SolverLoadTests(unittest.TestCase):
    def test_moment_cload_and_centrifugal_load_are_accepted(self):
        starter = os.environ.get('INP2RAD_STARTER', STARTER)
        if not os.path.isfile(starter):
            self.skipTest(f'starter not found at {starter}')
        with tempfile.TemporaryDirectory() as folder:
            inp_path = os.path.join(folder, 'loadcase.inp')
            with open(inp_path, 'w') as handle:
                handle.write(DECK)
            converter.or_gui = True
            converter.run_timer = False
            self.assertTrue(converter.start(inp_path), 'conversion failed')

            starter_input = 'loadcase_0000.rad'
            result = subprocess.run(
                [starter, '-i', starter_input, '-nt', '1', '-np', '1'],
                cwd=folder, env=solver_environment(), capture_output=True, text=True,
                timeout=180)
            listing_path = os.path.join(folder, 'loadcase_0000.out')
            listing = ''
            if os.path.isfile(listing_path):
                with open(listing_path, errors='replace') as handle:
                    listing = handle.read()

            self.assertEqual(result.returncode, 0,
                             f'starter failed:\n{result.stdout}\n{result.stderr}')
            self.assertNotIn('ERROR ID', result.stdout)
            self.assertIn('0 ERROR(S)', result.stdout)
            # The starter echo table proves both loads were actually read.
            self.assertIn('    XX ', listing)
            self.assertIn('  100.0000000000', listing)  # angular velocity, not sqrt
            self.assertIn('CENTRIFUGAL LOAD', listing)
            self.assertIn('  YY ', listing)


if __name__ == '__main__':
    unittest.main()
