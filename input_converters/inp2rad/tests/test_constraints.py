# Copyright (C) 2026 SISW Siemens Industry Software Inc.
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
"""Tie, rigid-body, coupling and MPC tests (non-element, no solver)."""
from support import ConverterTestCase, lines, joined, inp2rad


class DistributingCouplingTests(ConverterTestCase):
    def test_coupling_without_dcoupe3d_emits_discoup(self):
        # P0: the old code tested a stale refnode from the last DCOUP3D and
        # silently dropped this coupling.
        out = inp2rad.convert_distcoup(lines("""
*COUPLING, REF NODE=100, SURFACE=CPS
*DISTRIBUTING
1, 1.0
2, 2.0
*SURFACE, NAME=CPS, TYPE=NODE
1, 0.0
2, 0.0
"""))
        text = joined(out)
        self.assertIn("*DISCOUP, ID=placeholder", text)
        self.assertIn("CPS", text)
        self.assertIn("100", text)

    def test_dcoupe3d_path_still_works(self):
        out = inp2rad.convert_distcoup(lines("""
*ELEMENT, TYPE=DCOUP3D, ELSET=DC1
5, 100
*DISTRIBUTING COUPLING, ELSET=DC1
10, 1.0
"""))
        text = joined(out)
        self.assertIn("*DISCOUP, ID=5", text)
        self.assertIn("nodeset_for_10", text)

    def test_generated_discoup_becomes_rbe3(self):
        out = inp2rad.convert_distcoup(lines("""
*COUPLING, REF NODE=100, SURFACE=CPS
*DISTRIBUTING
1, 1.0
*SURFACE, NAME=CPS, TYPE=NODE
1, 0.0
"""))
        nsets, _, _ = inp2rad.convert_nsets(out, {})
        rbe3, _ = inp2rad.convert_discoup(out, nsets, 50)
        text = joined(rbe3)
        self.assertIn("/RBE3/", text)
        self.assertIn("100", text)

    def test_bad_discoup_data_is_skipped_with_warnings(self):
        out = inp2rad.convert_discoup(lines("""
*DISCOUP, ID=9
DC1
2
100
UnknownSet, 1.0
BadLine
"""), {"Other": {"id": 2}}, 5)
        text = joined(out[0])
        # P0 (review): the whole coupling is skipped when no weight row is
        # valid; no /RBE3 with N_set=2 and zero weight rows is emitted.
        self.assertEqual(text, "")
        self.assertIn("no valid weight rows", self.printed)
        self.assertIn("unknown NSET", self.printed)
        self.assertIn("malformed *DISCOUP", self.printed)

    def test_partially_valid_discoup_uses_actual_weight_count(self):
        out = inp2rad.convert_discoup(lines("""
*DISCOUP, ID=9
DC1
2
100
Good, 2.5
UnknownSet, 1.0
"""), {"Good": {"id": 4}}, 5)
        text = joined(out[0])
        self.assertIn("/RBE3/9", text)
        self.assertIn("       100                   1         1",
                      text)  # N_set=1, not the declared 2
        self.assertIn("111 000", text)
        self.assertIn("declared 2 weight", self.printed)


class TieTests(ConverterTestCase):
    SURFS = {"Main": 4, "Main2": 6}

    def test_node_to_surface_tie(self):
        out, inter = inp2rad.convert_ties(
            lines("*TIE, NAME=T1, TYPE=NODE TO SURFACE, POSITION TOLERANCE=0.01\nSlaves, Main\n"),
            self.SURFS, {"Slaves___nodes": {"id": 7}}, 0)
        text = joined(out)
        self.assertEqual(inter, 1)
        self.assertIn("/INTER/TYPE2/1", text)
        self.assertIn("T1", text)
        self.assertIn("0.01", text)
        self.assertIn("         7         4", text)

    def test_surface_to_surface_tie(self):
        out, inter = inp2rad.convert_ties(
            lines("*TIE, NAME=T2, TYPE=SURFACE TO SURFACE\nS1, Main\n"),
            {"Main": 4, "S1": 9}, {}, 2)
        text = joined(out)
        self.assertEqual(inter, 3)
        self.assertIn("/INTER/TYPE2/3", text)
        self.assertIn("         0         4", text)  # Surf_IDm first
        self.assertIn("         9", text)             # Surf_IDs

    def test_state_is_not_reused_by_next_tie(self):
        out, inter = inp2rad.convert_ties(lines("""
*TIE, NAME=T1, TYPE=NODE TO SURFACE
S1, Main
*TIE, NAME=T2, TYPE=SURFACE TO SURFACE
S2, Main2
"""), {"Main": 4, "Main2": 6, "S1": 9, "S2": 10},
            {"S1___nodes": {"id": 7}, "S2___nodes": {"id": 8}}, 0)
        text = joined(out)
        self.assertEqual(inter, 2)
        self.assertIn("/INTER/TYPE2/1\nT1", text)
        self.assertIn("/INTER/TYPE2/2\nT2", text)

    def test_raw_nset_fallback_for_node_side(self):
        out, inter = inp2rad.convert_ties(
            lines("*TIE, NAME=T1\nRawNodes, Main\n"),
            self.SURFS, {"RawNodes": {"id": 12}}, 0)
        self.assertEqual(inter, 1)
        self.assertIn("12         4", joined(out))
        self.assertIn("raw/fallback node group", self.printed)

    def test_malformed_tie_line_does_not_raise(self):
        out, inter = inp2rad.convert_ties(
            lines("*TIE, NAME=T1\nOnlyOneField\n"), self.SURFS, {}, 0)
        self.assertEqual(inter, 0)
        self.assertEqual(out, [])
        self.assertIn("malformed *TIE", self.printed)

    def test_unknown_tie_surface_warns_and_skips(self):
        out, inter = inp2rad.convert_ties(
            lines("*TIE, NAME=T1\nSlaves, Missing\n"),
            {}, {"Slaves___nodes": {"id": 7}}, 0)
        self.assertEqual(inter, 0)
        self.assertIn("could not be converted", self.printed)

    def test_2023_s2s_emits_symmetric_interface(self):
        inp2rad.radversion = 2023
        out, inter = inp2rad.convert_ties(
            lines("*TIE, NAME=T2, TYPE=SURFACE TO SURFACE\nS1, Main\n"),
            {"Main": 4, "S1": 9},
            {"Main___nodes": {"id": 7}, "S1___nodes": {"id": 8}}, 0)
        self.assertEqual(inter, 2)
        self.assertIn("T2_symm", joined(out))


class RigidBodyTests(ConverterTestCase):
    def test_rigid_body_by_property(self):
        props = {"Tool": {"prop_id": 1, "part_id": 2, "nint": "998"}}
        mats = {"Tool": {"material_id": 1, "rho": 7.8e-9}}
        out, nset_counter, max_elem, _, _ = inp2rad.convert_rigids(
            lines("*RIGID BODY, ELSET=Tool, REF NODE=5, DENSITY=7.8e-9\n"),
            props, mats, {}, 10, {}, [], 100)
        text = joined(out)
        self.assertIn("/RBODY/101", text)
        self.assertIn("/GRNOD/PART/11", text)
        self.assertIn("/GRNOD/NODE/12", text)
        self.assertEqual((nset_counter, max_elem), (12, 101))

    def test_rigid_body_by_nset(self):
        out, nset_counter, _, _, _ = inp2rad.convert_rigids(
            lines("*RIGID BODY, NSET=ToolNodes, REF NODE=7\n"),
            {}, {}, {"ToolNodes": {"id": 3}}, 10, {}, [], 100)
        text = joined(out)
        self.assertIn("/RBODY/101", text)
        self.assertIn("/GRNOD/NODE/11", text)
        self.assertEqual(nset_counter, 11)

    def test_rigid_body_by_rigid_elset(self):
        out, _, _, _, _ = inp2rad.convert_rigids(
            lines("*RIGID BODY, ELSET=ToolEl, REF NODE=9\n"),
            {}, {}, {"ToolEl___grnod": {"id": 4}}, 10,
            {"ToolEl": [1, 2]}, [], 100)
        self.assertIn("/RBODY/101", joined(out))

    def test_missing_elset_and_nset_warns_instead_of_crashing(self):
        out, _, _, _, _ = inp2rad.convert_rigids(
            lines("*RIGID BODY, REF NODE=5\n"), {}, {}, {}, 0, {}, [], 10)
        self.assertEqual(out, [])
        self.assertIn("neither ELSET= nor NSET=", self.printed)

    def test_malformed_block_does_not_inherit_previous_rigid_state(self):
        props = {"Tool": {"prop_id": 1, "part_id": 2, "nint": "998"}}
        mats = {"Tool": {"material_id": 1, "rho": 7.8e-9}}
        deck = lines("""
*RIGID BODY, ELSET=Tool, REF NODE=5
*RIGID BODY, REF NODE=6
""")
        out, _, _, _, _ = inp2rad.convert_rigids(
            deck, props, mats, {}, 0, {}, [], 100)
        card_text = joined(out)
        self.assertEqual(card_text.count("/RBODY/"), 1)
        self.assertIn("/RBODY/101", card_text)
        self.assertIn("neither ELSET= nor NSET=", self.printed)

    def test_missing_ref_node_warns_instead_of_crashing(self):
        out, _, _, _, _ = inp2rad.convert_rigids(
            lines("*RIGID BODY, ELSET=Tool\n"),
            {"Tool": {"prop_id": 1, "part_id": 1, "nint": "998"}},
            {}, {}, 0, {}, [], 10)
        self.assertEqual(out, [])
        self.assertIn("no REF NODE", self.printed)


class CouplingTests(ConverterTestCase):
    def test_kinematic_coupling_creates_rbody(self):
        deck = lines("*KINEMATIC COUPLING, REF NODE=100\n1001, 1002\n")
        nsets, _, out_lines = inp2rad.convert_nsets(deck, {})
        out, max_elem = inp2rad.convert_coupling(out_lines, nsets, 10)
        self.assertEqual(max_elem, 11)
        self.assertIn("/RBODY/11", joined(out))
        self.assertIn("KINEMATIC COUPLING for REF NODE 100", joined(out))

    def test_coupling_constraint_creates_rbody(self):
        out, max_elem = inp2rad.convert_coupling(
            lines("*COUPLING, CONSTRAINT NAME=C1, REF NODE=100, SURFACE=CPS\n"),
            {"CPS___nodes": {"id": 7}}, 10)
        self.assertEqual(max_elem, 11)
        self.assertIn("/RBODY/11\nC1", joined(out))

    def test_unknown_coupling_node_set_warns(self):
        out, _ = inp2rad.convert_coupling(
            lines("*COUPLING, CONSTRAINT NAME=C1, REF NODE=100, SURFACE=Missing\n"),
            {}, 10)
        self.assertEqual(out, [])
        self.assertIn("references no known node set", self.printed)


class MPCTests(ConverterTestCase):
    def test_tie_spring_and_beam_rigid(self):
        inp2rad.e_magnitude = 210000.0
        inp2rad.rho_magnitude = 7.8e-9
        ties, rigids, prop_id, max_elem = inp2rad.convert_mpc_ties(
            lines("*MPC\nTIE, 1, 2\nBEAM, 3, 4\n"), 9, 100)
        text = joined(ties)
        self.assertIn("/PART/9", text)
        self.assertIn("/PROP/TYPE13/9", text)
        self.assertIn("/SPRING/9", text)
        self.assertIn("         1         2", text)
        self.assertEqual(rigids, [("3", "4")])
        self.assertEqual((prop_id, max_elem), (9, 102))

    def test_hinge_and_pin_supported_with_warning(self):
        inp2rad.e_magnitude = 210000.0
        inp2rad.rho_magnitude = 7.8e-9
        _, rigids, _, _ = inp2rad.convert_mpc_ties(
            lines("*MPC\nHINGE, 5, 6\nPIN, 7, 8\n"), 9, 0)
        self.assertEqual(rigids, [("5", "6"), ("7", "8")])
        self.assertIn("rotational releases", self.printed)

    def test_unsupported_mpc_type_is_warned(self):
        inp2rad.e_magnitude = 210000.0
        inp2rad.rho_magnitude = 7.8e-9
        inp2rad.convert_mpc_ties(lines("*MPC\nBAR, 1, 2\n"), 9, 0)
        self.assertIn("unsupported *MPC type 'BAR'", self.printed)

    def test_malformed_mpc_line_skipped(self):
        inp2rad.e_magnitude = 210000.0
        inp2rad.rho_magnitude = 7.8e-9
        ties, rigids, _, _ = inp2rad.convert_mpc_ties(
            lines("*MPC\nTIE, 1\n"), 9, 0)
        self.assertEqual(ties, [])
        self.assertEqual(rigids, [])
        self.assertIn("malformed *MPC", self.printed)

    def test_default_calibration_warning_when_no_material(self):
        # e_magnitude/rho_magnitude are still at the module defaults.
        inp2rad.convert_mpc_ties(lines("*MPC\nTIE, 1, 2\n"), 9, 0)
        self.assertIn("calibrated with default", self.printed)


if __name__ == "__main__":
    import unittest
    unittest.main()
