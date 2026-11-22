"""Two-step time mapping tests for BCs, gravity and pressure loads."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import inp2rad.inp2rad as converter  # noqa: E402


def two_step_deck():
    return [
        '*AMPLITUDE, NAME=A\n', '0, 0, 1, 1\n',
        '*STEP\n', '*STATIC\n', '1.0, 1., 1.\n',
        '*BOUNDARY, TYPE=VELOCITY, AMPLITUDE=A\n', 'MOVE, 1, 2.0\n',
        '*DLOAD, AMPLITUDE=A\n', 'PART, GRAV, 9.81, 0., 0., -1.\n',
        '*DSLOAD, AMPLITUDE=A\n', 'SET_A, P, 1.0\n',
        '*END STEP\n',
        '*STEP\n', '*STATIC\n', '2.0, 1., 1.\n',
        '*BOUNDARY, TYPE=VELOCITY, AMPLITUDE=A\n', 'MOVE, 1, 3.0\n',
        '*DLOAD, AMPLITUDE=A\n', 'PART, GRAV, 9.81, 0., 0., -1.\n',
        '*DSLOAD, AMPLITUDE=A\n', 'SET_A, P, 2.0\n',
        '*END STEP\n',
    ]


class StepMappingTests(unittest.TestCase):
    def setUp(self):
        self.deck = two_step_deck()
        self.nsets = {'MOVE': {'id': 4, 'values': [1, 2], 'is_referenced': True}}
        self.props = {'PART': {'prop_id': 1, 'part_id': 1}}
        self.elsets = {'SET_A': [1, 2]}
        self.segments = {1: {'spos': [1, 2, 3, 4]}, 2: {'spos': [5, 6, 7, 8]}}

    def test_parse_two_steps(self):
        self.assertEqual(converter.parse_step_info(self.deck),
                         [{'start': 0.0, 'period': 1.0},
                          {'start': 1.0, 'period': 2.0}])

    def test_boundary_windows_and_shift(self):
        functs, fct_id = converter.read_amplitudes(self.deck, 20)
        blocks, _, _ = converter.convert_boundary(
            self.deck, 10, self.nsets, functs, fct_id)
        text = '\n'.join(blocks)
        self.assertEqual(text.count('/IMPVEL/'), 2)
        # Step 1 -> [0, 1]; step 2 -> [1, 3] (global Radioss time).
        self.assertIn('                   0                   1', text)
        self.assertIn('                   1                   3', text)
        self.assertIn('A__step_t1', functs)
        self.assertEqual(functs['A__step_t1']['data'], [(1.0, 0.0), (2.0, 1.0)])

    def test_gravity_uses_second_step_shift(self):
        functs, fct_id = converter.read_amplitudes(self.deck, 20)
        blocks, _, _ = converter.convert_dloads(
            self.deck, 10, {}, self.props, functs, fct_id)
        self.assertEqual('\n'.join(blocks).count('/GRAV/'), 2)
        self.assertIn('A__step_t1', functs)
        self.assertEqual(functs['A__step_t1']['data'], [(1.0, 0.0), (2.0, 1.0)])

    def test_pressure_uses_second_step_shift(self):
        functs, fct_id = converter.read_amplitudes(self.deck, 20)
        blocks, _, _, _ = converter.convert_pload(
            self.deck, 10, 5, {}, self.elsets, self.segments, functs, fct_id)
        self.assertEqual('\n'.join(blocks).count('/PLOAD/'), 2)
        self.assertIn('A__step_t1', functs)
        self.assertEqual(functs['A__step_t1']['data'], [(1.0, 0.0), (2.0, 1.0)])


if __name__ == '__main__':
    unittest.main()
