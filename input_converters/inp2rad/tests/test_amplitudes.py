"""Focused tests for amplitude parsing (no solver required)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import inp2rad.inp2rad as converter  # noqa: E402


class AmplitudeTests(unittest.TestCase):
    def test_tabular_header_with_trailing_comma_and_type(self):
        lines = [
            '*AMPLITUDE, NAME=A1, TYPE=TABULAR,\n',
            '0.0, 0.0, 1.0, 1.0, 2.0, 0.5\n',
            '*STEP\n',
        ]
        functs, next_id = converter.read_amplitudes(lines, 10)
        self.assertEqual(functs['A1']['id'], 11)
        self.assertEqual(functs['A1']['definition'], 'TABULAR')
        self.assertEqual(functs['A1']['data'], [(0.0, 0.0), (1.0, 1.0), (2.0, 0.5)])
        self.assertEqual(next_id, 12)
        self.assertIn('DEFAULT CONSTANT OVER STEP', functs)

    def test_smooth_step_is_sampled(self):
        lines = [
            '*AMPLITUDE, NAME=SMOOTH, DEFINITION=SMOOTH STEP\n',
            '0.0, 0.0, 1.0, 2.0\n',
        ]
        functs, _ = converter.read_amplitudes(lines, 0)
        data = functs['SMOOTH']['data']
        self.assertGreater(len(data), 3)
        self.assertEqual(data[0], (0.0, 0.0))
        self.assertEqual(data[-1], (1.0, 2.0))
        # Smooth step has zero slope at both ends: mid point is exactly half.
        middle = [value for time, value in data if abs(time - 0.5) < 1e-9]
        self.assertAlmostEqual(middle[0], 1.0)
        for time, value in data:
            self.assertGreaterEqual(value, -1e-9)
            self.assertLessEqual(value, 2.0 + 1e-9)

    def test_smooth_step_uses_quintic_polynomial(self):
        data = converter.sample_smooth_step([(0.0, 0.0), (1.0, 1.0)],
                                            samples_per_interval=20)
        value_at_quarter = dict(data)[0.25]
        # xi=0.25: 0.25^3 * (10 - 15*0.25 + 6*0.25^2) = 0.103515625
        self.assertAlmostEqual(value_at_quarter, 0.103515625, places=9)
        self.assertNotAlmostEqual(value_at_quarter, 0.15625, places=4)

    def test_decay_before_t0_is_constant_a0(self):
        data = converter.sample_decay([2.0, 3.0, 1.0, 0.5], samples=10)
        self.assertIn((0.0, 2.0), data)
        self.assertIn((1.0, 2.0), data)
        before = [value for time, value in data if time < 1.0]
        self.assertTrue(before)
        self.assertTrue(all(abs(value - 2.0) < 1e-12 for value in before))
        # At t0 the decay term starts from A0 + A.
        self.assertIn((1.0, 5.0), data)

    def test_name_and_param_parsing_with_quotes_or_spaces(self):
        lines = [
            '*AMPLITUDE, NAME="My Amp, One", DEFINITION="SMOOTH STEP",\n',
            '0, 0, 1, 1\n',
        ]
        functs, _ = converter.read_amplitudes(lines, 0)
        self.assertIn('My Amp, One', functs)
        self.assertEqual(functs['My Amp, One']['definition'], 'SMOOTH STEP')
        self.assertEqual(converter.get_keyword_param('X=ok, Y="a,b"', 'Y'), 'a,b')

    def test_exponential_and_aggregate_forms(self):
        exp_lines = [
            '*AMPLITUDE, NAME=EXP, TYPE=EXPONENTIAL\n',
            '0.0, 0.0, 1.0, 1.0, 2.0\n',
        ]
        exp_data = converter.read_amplitudes(exp_lines, 0)[0]['EXP']['data']
        self.assertGreater(len(exp_data), 3)
        self.assertEqual(exp_data[0], (0.0, 0.0))
        self.assertEqual(exp_data[-1], (1.0, 1.0))

        agg_lines = [
            '*AMPLITUDE, NAME=AGG, DEFINITION=AGGREGATE\n',
            '1.0, 0.5\n',
            '2.0, 1.5\n',
        ]
        agg_data = converter.read_amplitudes(agg_lines, 0)[0]['AGG']['data']
        self.assertEqual(agg_data[-1], (1.5, 3.0))

    def test_equally_spaced(self):
        lines = [
            '*AMPLITUDE, NAME=EQ, DEFINITION=EQUALLY SPACED, FIXED INTERVAL=0.25, BEGIN=1.0\n',
            '1.0, 2.0, 3.0\n',
        ]
        data = converter.read_amplitudes(lines, 0)[0]['EQ']['data']
        self.assertEqual(data, [(1.0, 1.0), (1.25, 2.0), (1.5, 3.0)])

    def test_unknown_amplitude_does_not_reference_function_1(self):
        functs, _ = converter.read_amplitudes(['*AMPLITUDE, NAME=A, DEFINITION=TABULAR\n', '0,0\n'], 5)
        default_id = functs['DEFAULT CONSTANT OVER STEP']['id']
        resolved, _ = converter.resolve_function_id('MISSING', functs, '*CLOAD', 99)
        self.assertEqual(resolved, default_id)
        self.assertNotEqual(resolved, 1)

    def test_multi_step_amplitude_time_shift(self):
        lines = [
            '*STEP\n', '*STATIC\n', '1.0, 1., 1.\n',
            '*BOUNDARY, TYPE=VELOCITY, AMPLITUDE=A\n', '1, 1, 0.5\n',
        ]
        steps = converter.parse_step_info(lines)
        self.assertEqual(steps, [{'start': 0.0, 'period': 1.0}])
        functs, _ = converter.read_amplitudes(
            ['*AMPLITUDE, NAME=A\n', '0, 0, 1, 1\n'], 20)
        shifted_id, _ = converter.resolve_function_id(
            'A', functs, '*BOUNDARY', 30, step_start=5.0)
        self.assertEqual(functs[shifted_id if isinstance(shifted_id, str) else 'A__step_t5']['id'], shifted_id)
        self.assertEqual(functs['A__step_t5']['data'], [(5.0, 0.0), (6.0, 1.0)])


if __name__ == '__main__':
    unittest.main()
