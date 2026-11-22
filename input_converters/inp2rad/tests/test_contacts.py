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
"""Surface and contact-conversion tests (non-element, no solver)."""
from unittest import mock

from support import ConverterTestCase, lines, joined, inp2rad


def element_block(element_type, elements):
    """Build the ``element_dicts`` structure used by convert_segments."""
    return {element_type: [{"elements": [
        {"element_id": eid, "nodes": nodes} for eid, nodes in elements
    ]}]}


class SurfaceSegmentTests(ConverterTestCase):
    def test_degraded_shell_segments(self):
        elements = element_block("S6", [(1, [1, 2, 3, 4, 5, 6])])
        elements.update(element_block("S8", [(2, [11, 12, 13, 14, 15, 16, 17, 18])]))
        seg = inp2rad.convert_segments(elements)
        # sneg is the reversed corner loop; nodes 4..6 / 5..8 are mid-side
        # nodes of a shell and are NOT the opposite face.
        self.assertEqual(seg[1]["spos"], [1, 2, 3])
        self.assertEqual(seg[1]["sneg"], [3, 2, 1])
        self.assertEqual(seg[2]["spos"], [11, 12, 13, 14])
        self.assertEqual(seg[2]["sneg"], [14, 13, 12, 11])

    def test_line_and_beam_segments(self):
        elements = element_block("S2", [(1, [1, 2])])
        elements.update(element_block("B32", [(2, [3, 4, 5])]))
        seg = inp2rad.convert_segments(elements)
        self.assertEqual(seg[1], {"spos": [1, 2], "sneg": [2, 1]})
        self.assertEqual(seg[2], {"spos": [3, 5], "sneg": [5, 3]})

    def test_numeric_shell_face_ids_map_to_spos_sneg(self):
        seg = {1: {"spos": [10, 11, 12], "sneg": [12, 11, 10]}}
        for face, expected in (("1", [10, 11, 12]), ("2", [12, 11, 10])):
            with self.subTest(face=face):
                out = inp2rad.parse_surface_data(
                    lines(f"*SURFACE, NAME=Surf, TYPE=ELEMENT\n1, {face}\n"),
                    {}, 0, {}, seg, {})
                node_lines = [ln for ln in out[0] if "10" in ln or "12" in ln]
                self.assertTrue(any(
                    "10        11        12" in ln for ln in node_lines
                ) if face == "1" else any(
                    "12        11        10" in ln for ln in node_lines
                ))

    def test_solid_numeric_face_maps_to_s1(self):
        seg = {2: {"s1": [20, 21, 22], "s2": [23, 24, 25]}}
        out = inp2rad.parse_surface_data(
            lines("*SURFACE, NAME=Surf, TYPE=ELEMENT\n2, 1\n"),
            {}, 0, {}, seg, {})
        self.assertTrue(any("20        21        22" in ln for ln in out[0]))

    def test_blank_side_surface_uses_registered_id_once(self):
        props = {"PartA": {"prop_id": 1, "part_id": 1, "nint": "999"}}
        out = inp2rad.parse_surface_data(
            lines("*SURFACE, NAME=Surf, TYPE=ELEMENT\n,\n"),
            {}, 5, {}, {}, props)
        surface_lines, surf_id, surf_map = out[0], out[1], out[2]
        # parse_surface_data allocates its own surface ids from 1.
        self.assertEqual(surf_id, 1)
        self.assertEqual(surf_map["Surf"], 1)
        part_ext = [ln for ln in surface_lines if "/SURF/PART/EXT/" in ln]
        self.assertEqual(len(part_ext), 1)
        self.assertIn("/SURF/PART/EXT/1", part_ext[0])

    def test_part_ext_buffer_is_reset_between_surfaces(self):
        props = {
            "PartA": {"prop_id": 1, "part_id": 1, "nint": "999"},
            "PartB": {"prop_id": 2, "part_id": 2, "nint": "999"},
        }
        out = inp2rad.parse_surface_data(lines("""
*SURFACE, NAME=Surf1, TYPE=ELEMENT
,
*SURFACE, NAME=Surf2, TYPE=ELEMENT
,
"""), {}, 0, {}, {}, props)
        surface_lines = out[0]
        part_rows = [ln for ln in surface_lines if ln.strip() == "1         2"]
        # Each all-parts surface lists every part exactly once.  Without the
        # P0 prop_lines reset the second surface inherited the first one's
        # row and emitted it twice.
        self.assertEqual(len(part_rows), 2)
        self.assertEqual([ln for ln in surface_lines
                          if "/SURF/PART/EXT/" in ln],
                         ["/SURF/PART/EXT/1\nSurf1",
                          "/SURF/PART/EXT/2\nSurf2"])

    def test_node_surface_header_survives_convert_nsets_without_surf_id(self):
        deck = lines("*SURFACE, NAME=NodeSurf, TYPE=NODE\n1, 0.0\n3, 0.0\n")
        nsets, _, out_lines = inp2rad.convert_nsets(deck, {})
        self.assertTrue(any(ln.lower().startswith("*surface")
                            for ln in out_lines))
        out = inp2rad.parse_surface_data(out_lines, {}, 5, nsets, {}, {})
        # Node-group ids are NOT /SURF ids: contact pairs and pload must not
        # pick them up from surf_name_to_id.  Ties use the nsets alias.
        self.assertNotIn("NodeSurf", out[2])
        self.assertEqual(out[4]["NodeSurf___originalnodeset"]["id"],
                         nsets["NodeSurf"]["id"])
        self.assertIn("NOT a /SURF id", self.printed)

    def test_contact_pair_cannot_use_node_surface_as_surf_id(self):
        deck = lines("*SURFACE, NAME=NodeSurf, TYPE=NODE\n1, 0.0\n")
        nsets, _, out_lines = inp2rad.convert_nsets(deck, {})
        surf_out = inp2rad.parse_surface_data(out_lines, {}, 0, nsets, {}, {})
        surf_map = surf_out[2]
        self.assertNotIn("NodeSurf", surf_map)
        out, _, inter_id = inp2rad.convert_contacts(
            lines("*CONTACT PAIR, INTERACTION=Fric\nNodeSurf, ElemSurf\n"),
            {}, 0, {"Fric": "0.1"},
            dict(surf_map, ElemSurf=3))
        self.assertEqual(inter_id, 0)
        self.assertEqual(out, [])
        self.assertIn("unknown surface(s)", self.printed)

    def test_property_group_name_resolution(self):
        props = {
            "PartA": {"prop_id": 1, "part_id": 4,
                      "collecting_elset_name": "GroupA"},
        }
        self.assertEqual(
            inp2rad.resolve_contact_property_part_ids(props, "GroupA"), [4])
        self.assertEqual(
            inp2rad.resolve_contact_property_part_ids(props, '"PartA"'), [4])
        self.assertEqual(
            inp2rad.resolve_contact_property_part_ids(props, "Unknown"), [])

    def test_friction_and_rough_interaction_parsing(self):
        out = inp2rad.parse_surface_interaction_data(lines("""
*SURFACE INTERACTION, NAME=FricA
*FRICTION
0.25
*SURFACE INTERACTION, NAME=FricRough
*FRICTION, ROUGH
"""))
        self.assertEqual(out["FricA"], "0.25")
        self.assertEqual(out["FricRough"], 1.0)


class ContactPairTests(ConverterTestCase):
    SURFS = {"SurfA": 1, "SurfB": 2, "SurfC": 3, "SurfD": 4}

    def test_pair_emits_type24_with_friction(self):
        out, surf_id, inter_id = inp2rad.convert_contacts(
            lines("*CONTACT PAIR, INTERACTION=FricA\nSurfA, SurfB\n"),
            {}, 0, {"FricA": "0.3"}, self.SURFS)
        self.assertEqual(inter_id, 1)
        self.assertIn("/INTER/TYPE24/1", joined(out))
        self.assertIn("0.3", joined(out))
        self.assertIn("         2         1", joined(out))

    def test_consecutive_pairs_keep_their_own_friction(self):
        out, _, inter_id = inp2rad.convert_contacts(lines("""
*CONTACT PAIR, INTERACTION=FricA
SurfA, SurfB
*CONTACT PAIR, INTERACTION=FricB
SurfC, SurfD
"""), {}, 0, {"FricA": "0.1", "FricB": "0.9"}, self.SURFS)
        self.assertEqual(inter_id, 2)
        self.assertEqual(joined(out).count("/INTER/TYPE24/"), 2)
        self.assertEqual(joined(out).count("0.1"), 1)
        self.assertEqual(joined(out).count("0.9"), 1)

    def test_unknown_surface_warns_and_skips_without_hanging(self):
        # Previously this left ``contactpair`` True forever and looped on the
        # same line: the test would never finish.  Now the line is consumed.
        out, _, inter_id = inp2rad.convert_contacts(lines("""
*CONTACT PAIR, INTERACTION=FricA
SurfA, Missing
*CONTACT PAIR, INTERACTION=FricB
SurfC, SurfD
"""), {}, 0, {"FricA": "0.1", "FricB": "0.9"}, self.SURFS)
        self.assertEqual(inter_id, 1)
        self.assertIn("/INTER/TYPE24/1\nFricB", joined(out))
        self.assertIn("unknown surface(s)", self.printed)

    def test_pair_without_interaction_is_skipped_with_warning(self):
        out, _, inter_id = inp2rad.convert_contacts(
            lines("*CONTACT PAIR\nSurfA, SurfB\n"),
            {}, 0, {}, self.SURFS)
        self.assertEqual(inter_id, 0)
        self.assertEqual(out, [])
        self.assertIn("without INTERACTION", self.printed)

    def test_malformed_pair_line_is_skipped(self):
        out, _, inter_id = inp2rad.convert_contacts(
            lines("*CONTACT PAIR, INTERACTION=FricA\nSurfA\n"),
            {}, 0, {"FricA": "0.1"}, self.SURFS)
        self.assertEqual(inter_id, 0)
        self.assertIn("malformed *CONTACT PAIR", self.printed)

    def test_general_contact_with_property_assignment_single_interface(self):
        props = {"PartA": {"prop_id": 1, "part_id": 1, "nint": "999"}}
        out, surf_id, inter_id = inp2rad.convert_contacts(lines("""
*CONTACT
*CONTACT PROPERTY ASSIGNMENT
PartA, , FricA
"""), props, 0, {"FricA": "0.4"}, {})
        self.assertEqual(inter_id, 1)
        self.assertEqual(surf_id, 1)
        text = joined(out)
        self.assertEqual(text.count("/INTER/TYPE24/"), 1)
        self.assertEqual(text.count("/SURF/PART/EXT/"), 1)
        self.assertIn("0.4", text)

    def test_general_contact_without_assignment_uses_zero_friction(self):
        props = {"PartA": {"prop_id": 1, "part_id": 1, "nint": "999"}}
        out, _, inter_id = inp2rad.convert_contacts(
            lines("*CONTACT\n"), props, 0, {}, {})
        self.assertEqual(inter_id, 1)
        self.assertIn("/INTER/TYPE24/1", joined(out))
        self.assertEqual(joined(out).count("/INTER/TYPE24/"), 1)

    def test_ppm_general_contact_uses_radioss_general_friction(self):
        out, _, inter_id = inp2rad.convert_contacts(
            lines("*SURFACE INTERACTION, NAME=RADIOSS_GENERAL\n"),
            {}, 0, {"RADIOSS_GENERAL": "0.2"}, {})
        self.assertEqual(inter_id, 1)
        self.assertIn("0.2", joined(out))
        self.assertIn("RADIOSS_GENERAL preset", joined(out))

    def test_exclusions_warn_without_blocking_for_input(self):
        with mock.patch("builtins.input", side_effect=AssertionError("prompted")):
            inp2rad.or_gui = False  # would prompt in the old implementation
            out, _, inter_id = inp2rad.convert_contacts(lines("""
*CONTACT EXCLUSIONS
SurfA, SurfB
*CONTACT PAIR, INTERACTION=FricA
SurfA, SurfB
"""), {}, 0, {"FricA": "0.1"}, self.SURFS)
        self.assertEqual(inter_id, 1)
        self.assertIn("EXCLUSIONS are not converted", self.printed)

    def test_contact_controls_tune_stfac_and_gap(self):
        out, _, _ = inp2rad.convert_contacts(lines("""
*CONTACT CONTROLS, STIFFNESS=1.2, GAP=0.5
*CONTACT PAIR, INTERACTION=FricA
SurfA, SurfB
"""), {}, 0, {"FricA": "0.1"}, self.SURFS)
        text = joined(out)
        self.assertIn("0.5", text)  # gap appears in Gap_max_s / Gap_max_m
        self.assertIn("1.2", text)  # stiffness appears in Stfac

    def test_rate_dependent_friction_and_cohesive_are_warned(self):
        inp2rad.convert_contacts(lines("""
*SURFACE INTERACTION, NAME=FricA
*FRICTION, DEPENDENCIES=2
0.1, 0.2
*COHESIVE BEHAVIOR
"""), {}, 0, {"FricA": "0.1"}, {})
        self.assertIn("rate/temperature", self.printed)
        self.assertIn("cohesive traction-separation", self.printed)

    def test_non_numeric_friction_falls_back_to_zero(self):
        out, _, _ = inp2rad.convert_contacts(
            lines("*CONTACT PAIR, INTERACTION=FricA\nSurfA, SurfB\n"),
            {}, 0, {"FricA": "banana"}, self.SURFS)
        self.assertIn("non-numeric friction", self.printed)
        self.assertIn("0", joined(out))


if __name__ == "__main__":
    import unittest
    unittest.main()
