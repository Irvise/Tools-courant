"""Focused tests for initial conditions."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import inp2rad.inp2rad as converter  # noqa: E402


def nsets():
    return {'MOVING': {'id': 12, 'values': [1, 2], 'is_referenced': True}}


class InitialConditionTests(unittest.TestCase):
    def test_velocity_header_with_trailing_parameters(self):
        lines = [
            '*INITIAL CONDITIONS, TYPE=VELOCITY, OP=NEW,\n',
            'MOVING, 1, 10.0\n',
            'MOVING, 2, 20.0\n',
        ]
        blocks, _ = converter.convert_initial(lines, 10, nsets())
        joined = '\n'.join(blocks)
        self.assertIn('/INIVEL/TRA/12', joined)
        self.assertIn('         10', joined)
        self.assertIn('         20', joined)

    def test_rotational_velocity(self):
        lines = [
            '*INITIAL CONDITIONS, TYPE=ROTATIONAL VELOCITY,\n',
            'MOVING, 3, 104.72\n',
        ]
        blocks, _ = converter.convert_initial(lines, 10, nsets())
        joined = '\n'.join(blocks)
        self.assertIn('/INIVEL/ROT/12', joined)
        self.assertIn('104.72', joined)

    def test_unresolved_nset_is_skipped(self):
        lines = ['*INITIAL CONDITIONS, TYPE=VELOCITY\n', 'MISSING, 1, 5.0\n']
        blocks, _ = converter.convert_initial(lines, 10, nsets())
        self.assertEqual(blocks, [])

    def test_numeric_nodes_are_grouped(self):
        lines = [
            '*INITIAL CONDITIONS, TYPE=VELOCITY\n',
            '1, 1, 3.0\n',
            '2, 1, 3.0\n',
        ]
        blocks, counter = converter.convert_initial(lines, 10, nsets())
        joined = '\n'.join(blocks)
        self.assertIn('/GRNOD/NODE/11', joined)
        self.assertIn('/INIVEL/TRA/11', joined)
        self.assertEqual(counter, 11)


if __name__ == '__main__':
    unittest.main()
