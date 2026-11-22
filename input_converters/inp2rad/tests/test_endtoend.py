"""End-to-end starter/engine generation for BC/load edge cases."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import inp2rad.inp2rad as converter  # noqa: E402


BASE_DECK = """*HEADING
BC regression deck
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
*AMPLITUDE, NAME=A
0., 0., 1., 1.
"""


def convert(deck_text, filename='e2e'):
    """Run start() in a temporary folder and return the generated starter text."""
    with tempfile.TemporaryDirectory() as folder:
        inp_path = os.path.join(folder, filename + '.inp')
        with open(inp_path, 'w') as handle:
            handle.write(deck_text)
        converter.or_gui = True
        converter.run_timer = False
        ok = converter.start(inp_path)
        if not ok:
            raise AssertionError('inp2rad conversion failed')
        with open(os.path.join(folder, filename + '_0000.rad')) as handle:
            return handle.read()


class EndToEndTests(unittest.TestCase):
    def test_named_surface_dsload_emits_pload(self):
        deck = BASE_DECK + """*SURFACE, NAME=TOP
1, S1
2, S1
*STEP
*STATIC
1.0, 1., 1.
*DSLOAD
TOP, P, 5.0
*END STEP
"""
        starter = convert(deck, 'named_surface')
        self.assertIn('/SURF/SEG/', starter)
        self.assertIn('/PLOAD/', starter)
        self.assertIn('Pressure Load TOP P', starter)

    def test_multi_step_and_mixed_gravity_targets(self):
        deck = BASE_DECK + """*STEP
*STATIC
1.0, 1., 1.
*BOUNDARY, TYPE=VELOCITY, AMPLITUDE=A
MOVE, 1, 2.0
*DLOAD
SOLIDS, GRAV, 9.81, 0., 0., -1.
*DLOAD
FIX, GRAV, 9.81, 0., 0., -1.
*END STEP
*STEP
*STATIC
2.0, 1., 1.
*BOUNDARY, TYPE=VELOCITY, AMPLITUDE=A
MOVE, 1, 3.0
*DLOAD
SOLIDS, GRAV, 9.81, 0., 0., -1.
*END STEP
"""
        starter = convert(deck, 'multi_step')
        grav_ids = [line.split('/')[-1] for line in starter.splitlines()
                    if line.startswith('/GRAV/')]
        skew_ids = [line.split('/')[-1] for line in starter.splitlines()
                    if line.startswith('/SKEW/FIX/')]
        self.assertEqual(len(grav_ids), 3)
        self.assertEqual(skew_ids, grav_ids)
        self.assertEqual(len(set(grav_ids)), 3)
        # Step 2 amplitude is shifted onto the global time axis and written.
        self.assertIn('A__step_t1', starter)
        self.assertIn('                   0                   1', starter)
        self.assertIn('                   1                   3', starter)


if __name__ == '__main__':
    unittest.main()
