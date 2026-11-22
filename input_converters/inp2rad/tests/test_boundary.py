"""Focused tests for boundary conditions and concentrated loads."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import inp2rad.inp2rad as converter  # noqa: E402


def nsets():
    return {
        'FIXED': {'id': 4, 'values': [1, 2, 3], 'is_referenced': True},
        'LOADSET': {'id': 7, 'values': [5, 6], 'is_referenced': True},
    }


def amplitudes():
    functs, fct_id = converter.read_amplitudes(
        ['*AMPLITUDE, NAME=A1\n', '0, 1, 1, 2\n'], 20)
    return functs, fct_id


class BoundaryTests(unittest.TestCase):
    def test_trailing_comma_in_type_and_amplitude(self):
        lines = [
            '*BOUNDARY, TYPE=VELOCITY, AMPLITUDE=A1,\n',
            'LOADSET, 1, 1, 2.5\n',
        ]
        blocks, counter, fct_id = converter.convert_boundary(
            lines, 10, nsets(), *amplitudes())
        joined = '\n'.join(blocks)
        self.assertIn('/IMPVEL/7', joined)
        self.assertIn('                 2.5 ', joined)
        self.assertNotIn('A1,', joined)

    def test_compact_three_field_imposed_velocity(self):
        lines = [
            '*BOUNDARY, TYPE=VELOCITY, AMPLITUDE=A1,\n',
            'LOADSET, 1, 2.5\n',
        ]
        blocks, _, _ = converter.convert_boundary(lines, 10, nsets(), *amplitudes())
        joined = '\n'.join(blocks)
        self.assertIn('/IMPVEL/7', joined)
        self.assertIn('                 2.5 ', joined)

    def test_symmetry_presets(self):
        lines = ['*BOUNDARY\n', 'FIXED, XSYMM\n']
        blocks, _, _ = converter.convert_boundary(lines, 10, nsets(), *amplitudes())
        self.assertIn('100 011', '\n'.join(blocks))
        self.assertIn('/BCS/4', '\n'.join(blocks))

    def test_impdisp_header_has_no_frame_field(self):
        lines = ['*BOUNDARY, TYPE=DISPLACEMENT, AMPLITUDE=A1\n', 'LOADSET, 1, 1, 0.5\n']
        blocks, _, _ = converter.convert_boundary(lines, 10, nsets(), *amplitudes())
        text = '\n'.join(blocks)
        self.assertIn('/IMPDISP/', text)
        self.assertIn('Gnod_id     Icoor', text)
        self.assertNotIn('Gnod_id     Frame     Icoor', text)

    def test_displacement_dof_range(self):
        lines = ['*BOUNDARY\n', 'FIXED, 1, 3\n']
        blocks, _, _ = converter.convert_boundary(lines, 10, nsets(), *amplitudes())
        self.assertIn('111 000', '\n'.join(blocks))

    def test_moment_load_uses_xx_direction(self):
        lines = ['*CLOAD, OP=NEW,\n', 'LOADSET, 4, 100.0\n']
        blocks, _, _ = converter.convert_boundary(lines, 10, nsets(), *amplitudes())
        joined = '\n'.join(blocks)
        self.assertIn('/CLOAD/7', joined)
        self.assertIn('        XX', joined)
        self.assertIn('Moment load', joined)

    def test_unresolved_nset_is_skipped(self):
        lines = ['*BOUNDARY\n', 'UNKNOWN_SET, PINNED\n', '*CLOAD\n', 'NO_SUCH_SET, 1, 5.0\n']
        blocks, _, _ = converter.convert_boundary(lines, 10, nsets(), *amplitudes())
        joined = '\n'.join(blocks)
        self.assertNotIn('/BCS/0', joined)
        self.assertNotIn('/CLOAD/0', joined)
        self.assertNotIn('UNKNOWN_SET', joined)
        self.assertNotIn('NO_SUCH_SET', joined)

    def test_system_skew_is_emitted_and_referenced(self):
        lines = [
            '*SYSTEM ID=3\n',
            '0., 0., 0., 1., 0., 0.\n',
            '0., 1., 0.\n',
            '*BOUNDARY, SYSTEM=3\n',
            'FIXED, ENCASTRE\n',
        ]
        skews = converter.build_system_skews(lines)
        self.assertTrue(any('/SKEW/FIX/3' in skew for skew in skews))
        blocks, _, _ = converter.convert_boundary(lines, 10, nsets(), *amplitudes())
        self.assertIn('         3', '\n'.join(blocks))


if __name__ == '__main__':
    unittest.main()
