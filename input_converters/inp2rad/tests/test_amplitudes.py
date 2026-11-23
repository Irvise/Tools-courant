"""Focused tests for amplitude parsing (no solver required)."""

import contextlib
import io
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

    def test_periodic_fourier_sampling(self):
        lines = [
            '*AMPLITUDE, NAME=P, DEFINITION=PERIODIC\n',
            '1, 6.283185307179586, 0., 0.\n',
            '1., 0.\n',
        ]
        data = converter.read_amplitudes(lines, 0)[0]['P']['data']
        self.assertGreater(len(data), 20)
        self.assertAlmostEqual(data[0][1], 1.0)  # cos(0) = 1
        peak = max(value for _, value in data)
        trough = min(value for _, value in data)
        self.assertAlmostEqual(peak, 1.0, places=6)
        self.assertAlmostEqual(trough, -1.0, places=6)

    def test_modulated_sampling(self):
        lines = [
            '*AMPLITUDE, NAME=M, DEFINITION=MODULATED\n',
            '1., 2., 0.5, 6.283185307179586, 12.566370614359172\n',
        ]
        data = converter.read_amplitudes(lines, 0)[0]['M']['data']
        self.assertGreater(len(data), 100)
        self.assertAlmostEqual(dict(data)[0.5], 1.0)
        before = [value for t, value in data if t < 0.5]
        self.assertTrue(before)
        self.assertTrue(all(abs(value - 1.0) < 1e-12 for value in before))

    def test_amplitude_scaling_parameters(self):
        lines = [
            '*AMPLITUDE, NAME=S, SCALEX=2, SCALEY=3, SHIFTX=1, SHIFTY=-0.5\n',
            '0, 1, 1, 2\n',
        ]
        data = converter.read_amplitudes(lines, 0)[0]['S']['data']
        self.assertEqual(data, [(1.0, 2.5), (3.0, 5.5)])

    def test_total_time_amplitude_is_not_shifted(self):
        lines = ['*AMPLITUDE, NAME=T, TIME=TOTAL TIME\n', '0, 0, 2, 1\n']
        functs, _ = converter.read_amplitudes(lines, 0)
        self.assertEqual(functs['T']['time'], 'TOTAL TIME')
        # With TIME=TOTAL TIME the amplitude is already on the global axis.
        blocks, _, _, _ = converter.convert_pload(
            ['*STEP\n', '*STATIC\n', '1., 1., 1.\n', '*DSLOAD, AMPLITUDE=T\n',
             'SET, P, 1.\n', '*END STEP\n', '*STEP\n', '*STATIC\n', '1., 1., 1.\n',
             '*DSLOAD, AMPLITUDE=T\n', 'SET, P, 1.\n'],
            10, 5, {}, {'SET': [1]}, {1: {'spos': [1, 2, 3]}}, functs, 20)
        self.assertEqual('\n'.join(blocks).count('/PLOAD/'), 2)
        # Only one function is needed: the total-time curve covers both steps.
        self.assertNotIn('T__step_t1', functs)
        self.assertEqual(functs['T']['data'], [(0.0, 0.0), (2.0, 1.0)])

    def test_unsupported_forms_warn_explicitly(self):
        for definition, data in (('USER', '1., 2.\n'),
                                 ('SOLUTION DEPENDENT', '0.5, 0.1, 100.\n'),
                                 ('ACTUATOR', '')):
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                functs = converter.read_amplitudes(
                    [f'*AMPLITUDE, NAME=U, DEFINITION={definition}\n', data], 0)[0]
            warning = stream.getvalue()
            self.assertIn(definition, warning)
            self.assertIn('### WARNING ###', warning)
            self.assertIn(functs['U']['id'], [f['id'] for f in functs.values()])


if __name__ == '__main__':
    unittest.main()
