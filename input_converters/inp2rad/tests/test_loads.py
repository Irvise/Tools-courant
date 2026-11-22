"""Focused tests for gravity, pressure and centrifugal loads."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import inp2rad.inp2rad as converter  # noqa: E402


def props():
    return {'PART_A': {'prop_id': 1, 'part_id': 1}, 'PART_B': {'prop_id': 2, 'part_id': 2}}


def amplitudes():
    functs, fct_id = converter.read_amplitudes([], 30)
    return functs, fct_id


class GravityTests(unittest.TestCase):
    def test_each_gravity_entry_keeps_its_own_direction_and_skew(self):
        lines = [
            '*DLOAD, AMPLITUDE=A1,\n',
            'PART_A, GRAV, 10.0, 0.0, 0.0, -1.0\n',
            '*DLOAD\n',
            'PART_B, GRAV, 20.0, 1.0, 0.0, 0.0\n',
        ]
        functs, fct_id = amplitudes()
        functs['A1'] = {'id': 31, 'data': [(0.0, 1.0), (1.0, 1.0)]}
        blocks, counter, _ = converter.convert_dloads(lines, 10, {}, props(), functs, fct_id)
        joined = '\n'.join(blocks)
        self.assertEqual(joined.count('/GRAV/'), 2)
        self.assertEqual(joined.count('/SKEW/FIX/'), 2)
        self.assertIn('                  20', joined)
        # Gravity along Z must not produce a degenerate skew direction.
        for line in joined.splitlines():
            if line.strip() and not line.startswith('#') and not line.startswith('/'):
                self.assertNotEqual(line.strip(), '0 0 0')

    def test_numeric_dload_target_does_not_discard_other_gravity(self):
        lines = [
            '*DLOAD\n',
            'P1, GRAV, 9.81, 0., 0., -1.\n',
            '42, GRAV, 9.81, 0., 0., -1.\n',
            'P2, GRAV, 9.81, 0., 0., -1.\n',
        ]
        blocks, _, _ = converter.convert_dloads(lines, 10, {}, props(), *amplitudes())
        self.assertEqual('\n'.join(blocks).count('/GRAV/'), 3)

    def test_mixed_targets_have_unique_skew_and_grav_ids(self):
        lines = [
            '*DLOAD\n',
            'PART_A, GRAV, 9.81, 0., 0., -1.\n',
        ]
        nsets = {'NODEV': {'id': 4, 'values': [1, 2], 'is_referenced': True}}
        lines += ['*DLOAD\n', 'NODEV, GRAV, 9.81, 0., 0., -1.\n']
        blocks, _, _ = converter.convert_dloads(
            lines, 10, nsets, props(), *amplitudes())
        joined = '\n'.join(blocks)
        skew_ids = [line.split('/')[-1] for line in joined.splitlines()
                    if line.startswith('/SKEW/FIX/')]
        grav_ids = [line.split('/')[-1] for line in joined.splitlines()
                    if line.startswith('/GRAV/')]
        self.assertEqual(len(skew_ids), 2)
        self.assertEqual(len(grav_ids), 2)
        self.assertEqual(skew_ids, grav_ids)
        self.assertEqual(len(set(skew_ids)), 2)

    def test_centrifugal_load(self):
        lines = [
            '*DLOAD\n',
            'PART_A, CENTRIF, 100.0, 0., 0., 0., 0., 0., 1.\n',
        ]
        blocks, _, _ = converter.convert_dloads(lines, 10, {}, props(), *amplitudes())
        joined = '\n'.join(blocks)
        self.assertIn('/LOAD/CENTRI/', joined)
        self.assertIn('ZZ', joined)
        self.assertIn('                  10', joined)


class PressureTests(unittest.TestCase):
    def setUp(self):
        self.segments = {
            1: {'s1': [1, 2, 3, 4], 's2': [5, 6, 7, 8], 'spos': [1, 2, 3, 4]},
            2: {'s1': [9, 10, 11, 12], 's2': [13, 14, 15, 16], 'spos': [9, 10, 11, 12]},
        }
        self.elsets = {'SET_A': [1, 2]}

    def test_p1_and_p2_on_same_elset_use_distinct_surfaces(self):
        lines = [
            '*DLOAD\n',
            'SET_A, P1, 1.0\n',
            'SET_A, P2, 2.0\n',
        ]
        blocks, counter, surf_id, _ = converter.convert_pload(
            lines, 10, 5, {}, self.elsets, self.segments, *amplitudes())
        joined = '\n'.join(blocks)
        self.assertEqual(joined.count('/SURF/SEG/'), 2)
        self.assertEqual(joined.count('/PLOAD/'), 2)
        self.assertIn('         1', joined)
        self.assertIn('         2', joined)

    def test_dsload_pressure_and_hydrostatic_approximation(self):
        lines = [
            '*DSLOAD\n',
            'SET_A, P, 3.0\n',
            'SET_A, HP, 4.0\n',
        ]
        blocks, _, _, _ = converter.convert_pload(
            lines, 10, 5, {}, self.elsets, self.segments, *amplitudes())
        joined = '\n'.join(blocks)
        self.assertEqual(joined.count('/PLOAD/'), 2)
        self.assertIn('SET_A type P', joined)
        self.assertIn('Pressure Load SET_A HP', joined)


if __name__ == '__main__':
    unittest.main()
