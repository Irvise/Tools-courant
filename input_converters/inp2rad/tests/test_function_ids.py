# Copyright (C) 2026 SISW Siemens Industry Software Inc.
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR
# IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""Fast regression tests for the shared /FUNCT identifier allocator.

Run with::

    python3 -m unittest discover -s input_converters/inp2rad/tests -v
"""

import os
import re
import sys
import tempfile
import unittest

MODULE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'inp2rad'))
if MODULE_DIR not in sys.path:
    sys.path.insert(0, MODULE_DIR)

import inp2rad  # noqa: E402  (path must be set up before importing)


DECK = """\
*NODE, NSET=ALLNODES
1, 0.0, 0.0, 0.0
2, 1.0, 0.0, 0.0
3, 0.0, 1.0, 0.0
4, 1.0, 1.0, 0.0
*ELEMENT, TYPE=S4, ELSET=ALLELEMS
1, 1, 2, 4, 3
*MATERIAL, NAME=STEEL
*DENSITY
7.85e-9
*ELASTIC
210000.0, 0.3
*PLASTIC
0.0, 200.0
0.1, 300.0
*SOLID SECTION, ELSET=ALLELEMS, MATERIAL=STEEL
0.0
*AMPLITUDE, NAME=LOAD_CURVE
0.0, 0.0
1.0, 1.0
2.0, 0.5
*NSET, NSET=LOADNODES
1
*CLOAD, AMPLITUDE=LOAD_CURVE
1, 2, 100.0
*DLOAD, GRAV=9.81
ALLELEMS, GRAV, 9.81, 0.0, -1.0, 0.0
*SURFACE, NAME=PRESS_SURF, TYPE=ELEMENT
ALLELEMS, S1
*DSLOAD
PRESS_SURF, P1, 50.0
*STEP
*END STEP
"""


def funct_ids(rad_text):
    """All /FUNCT card IDs in the order they appear in the deck."""
    return [int(value) for value in re.findall(r'^/FUNCT/(\d+)\s*$', rad_text, re.MULTILINE)]


def first_field_after(rad_text, header_start):
    """First field of the first data line following a card header comment."""
    lines = rad_text.splitlines()
    for index, line in enumerate(lines):
        if line.strip().startswith(header_start):
            for candidate in lines[index + 1:]:
                stripped = candidate.strip()
                if not stripped or stripped.startswith(('#', '/')):
                    continue
                return stripped.split()[0]
    return None


def fields_after(rad_text, header_start):
    """All fields of the first data line following a card header comment."""
    lines = rad_text.splitlines()
    for index, line in enumerate(lines):
        if line.strip().startswith(header_start):
            for candidate in lines[index + 1:]:
                stripped = candidate.strip()
                if not stripped or stripped.startswith(('#', '/')):
                    continue
                return stripped.split()
    return []


class FunctionIdAllocatorTests(unittest.TestCase):
    def convert_deck(self, deck_text):
        """Run a real inp2rad conversion on ``deck_text`` and return the starter."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            inp_path = os.path.join(tmp_dir, 'func_ids.inp')
            with open(inp_path, 'w') as inp_file:
                inp_file.write(deck_text)

            old_or_gui = inp2rad.or_gui
            old_timer = inp2rad.run_timer
            inp2rad.or_gui = True  # no interactive "Press Enter" prompt
            inp2rad.run_timer = False
            try:
                success = inp2rad.start(inp_path)
            finally:
                inp2rad.or_gui = old_or_gui
                inp2rad.run_timer = old_timer

            # unittest assertion (not a bare assert, which -O removes)
            self.assertTrue(success, 'inp2rad conversion failed')
            with open(os.path.join(tmp_dir, 'func_ids_0000.rad')) as rad_file:
                return rad_file.read()

    def test_allocator_sequence_observe_and_reset(self):
        allocator = inp2rad.FunctionIdAllocator()
        self.assertEqual([allocator.allocate() for _ in range(3)], [1, 2, 3])

        # Legacy callers may pass stale/zero fct_id values: they must not
        # rewind the allocator and cause the next ID to be reused.
        allocator.observe(0)
        allocator.observe(2)
        self.assertEqual(allocator.last_id, 3)
        self.assertEqual(allocator.allocate(), 4)

        allocator.reset()
        self.assertEqual(allocator.allocate(), 1)
        self.assertIs(inp2rad.get_function_id_allocator(), inp2rad.function_id_allocator)

    def test_material_and_amplitude_have_distinct_funct_ids(self):
        rad_text = self.convert_deck(DECK)
        ids = funct_ids(rad_text)

        # IDs are unique, and the numbering of existing decks is preserved:
        # plastic curve=1, amplitude=2, default amplitude=3, gravity=4, pload=5.
        self.assertEqual(len(ids), len(set(ids)), 'duplicate /FUNCT cards: %r' % ids)
        self.assertEqual(sorted(ids), [1, 2, 3, 4, 5])

        plastic_id = first_field_after(rad_text, '# func_ID1')
        cload_id = first_field_after(rad_text, '#  fct_IDT')
        grav_id = first_field_after(rad_text, '#funct_IDT')
        pload_fields = fields_after(rad_text, '#  surf_ID funct_IDp')

        self.assertEqual(plastic_id, '1')
        self.assertIn('/FUNCT/1', rad_text)
        self.assertEqual(cload_id, '2')
        self.assertRegex(rad_text, r'/FUNCT/2\s*\nLOAD_CURVE')
        self.assertEqual(grav_id, '4')
        self.assertEqual(pload_fields[1], '5')
        self.assertNotEqual(plastic_id, cload_id)

    def test_missing_amplitude_references_default_not_material_curve(self):
        deck = DECK.replace('*AMPLITUDE, NAME=LOAD_CURVE\n0.0, 0.0\n1.0, 1.0\n2.0, 0.5\n', '')
        deck = deck.replace('*CLOAD, AMPLITUDE=LOAD_CURVE', '*CLOAD')
        rad_text = self.convert_deck(deck)

        ids = funct_ids(rad_text)
        self.assertEqual(len(ids), len(set(ids)), 'duplicate /FUNCT cards: %r' % ids)
        # Plastic curve=1, generated default amplitude=2 (no explicit amplitudes).
        self.assertEqual(sorted(ids), [1, 2, 3, 4])
        self.assertEqual(first_field_after(rad_text, '#  fct_IDT'), '2')
        self.assertEqual(first_field_after(rad_text, '# func_ID1'), '1')

    def test_unknown_amplitude_on_gravity_uses_default_function(self):
        deck = DECK.replace('*AMPLITUDE, NAME=LOAD_CURVE\n0.0, 0.0\n1.0, 1.0\n2.0, 0.5\n', '')
        deck = deck.replace('*CLOAD, AMPLITUDE=LOAD_CURVE', '*CLOAD')
        deck = deck.replace('*DLOAD, GRAV=9.81', '*DLOAD, AMPLITUDE=MISSING_CURVE, GRAV=9.81')
        rad_text = self.convert_deck(deck)

        ids = funct_ids(rad_text)
        self.assertEqual(len(ids), len(set(ids)), 'duplicate /FUNCT cards: %r' % ids)
        # The default amplitude (/FUNCT/2) exists, so both loads must reference
        # it rather than the plastic curve (/FUNCT/1) or a missing curve.
        self.assertEqual(first_field_after(rad_text, '#  fct_IDT'), '2')
        self.assertEqual(first_field_after(rad_text, '#funct_IDT'), '2')
        self.assertRegex(rad_text, r'/FUNCT/2\s*\nDEFAULT CONSTANT OVER STEP')

    def test_unknown_amplitude_on_pressure_uses_default_function(self):
        deck = DECK.replace('*AMPLITUDE, NAME=LOAD_CURVE\n0.0, 0.0\n1.0, 1.0\n2.0, 0.5\n', '')
        deck = deck.replace('*DSLOAD\n', '*DSLOAD, AMPLITUDE=MISSING_PRESSURE\n')
        rad_text = self.convert_deck(deck)

        ids = funct_ids(rad_text)
        self.assertEqual(len(ids), len(set(ids)), 'duplicate /FUNCT cards: %r' % ids)
        # Plastic=1, default amplitude=2, gravity inline constant=3. PLOAD must
        # reuse /FUNCT/2, not allocate another pressure constant function.
        self.assertEqual(sorted(ids), [1, 2, 3])
        self.assertEqual(fields_after(rad_text, '#  surf_ID funct_IDp')[1], '2')
        self.assertNotIn('Pressure Constant', rad_text)
        self.assertRegex(rad_text, r'/FUNCT/2\s*\nDEFAULT CONSTANT OVER STEP')

    def test_empty_functs_dict_never_references_function_one(self):
        """Legacy/direct callers get a newly allocated default function."""
        allocator = inp2rad.FunctionIdAllocator()
        self.assertEqual(allocator.allocate(), 1)  # e.g. a material curve
        functs_dict = {}
        lines = ['*CLOAD, AMPLITUDE=MISSING\n', '1, 2, 100.0\n']

        boundary_blocks, _, last_id = inp2rad.convert_boundary(
            lines, 0, {}, functs_dict, 0, allocator
            )

        self.assertEqual(last_id, 2)
        self.assertEqual(functs_dict['DEFAULT CONSTANT OVER STEP']['id'], 2)
        boundary_text = '\n'.join(boundary_blocks)
        self.assertEqual(first_field_after(boundary_text, '#  fct_IDT'), '2')
        self.assertIn('/FUNCT/2', '\n'.join(inp2rad.write_functions(functs_dict)))

    def test_stale_fct_id_cannot_collide_across_producers(self):
        """Regression: producers passing an old-style fct_id=0 stay unique."""
        allocator = inp2rad.FunctionIdAllocator()
        lines = DECK.splitlines(keepends=True)

        materials, _, _, _ = inp2rad.convert_materials(lines, 0, allocator)
        plastic_id = materials['STEEL']['plastic_data']['rate_sets'][0]['fct_id']
        self.assertEqual(plastic_id, 1)

        # Old call sites restarted the numbering here and reused /FUNCT/1.
        amplitudes, _ = inp2rad.read_amplitudes(lines, 0, allocator)
        amplitude_id = amplitudes['LOAD_CURVE']['id']
        default_id = amplitudes['DEFAULT CONSTANT OVER STEP']['id']
        self.assertEqual([amplitude_id, default_id], [2, 3])

        dload_blocks, _, _ = inp2rad.convert_dloads(
            lines, 0, {}, {}, amplitudes, 0, allocator
            )
        gravity_id = int(re.search(r'/FUNCT/(\d+)', '\n'.join(dload_blocks)).group(1))

        pload_blocks, _, _, _ = inp2rad.convert_pload(
            lines, 0, 0, {'PRESS_SURF': 1}, {}, {}, amplitudes, 0, allocator
            )
        pressure_id = int(re.search(r'/FUNCT/(\d+)', '\n'.join(pload_blocks)).group(1))

        ids = [plastic_id, amplitude_id, default_id, gravity_id, pressure_id]
        self.assertEqual(ids, [1, 2, 3, 4, 5])
        self.assertEqual(len(ids), len(set(ids)))

    def test_global_allocator_survives_repeated_conversions(self):
        rad_first = self.convert_deck(DECK)
        rad_second = self.convert_deck(DECK)
        self.assertEqual(funct_ids(rad_first), funct_ids(rad_second))


if __name__ == '__main__':
    unittest.main()
