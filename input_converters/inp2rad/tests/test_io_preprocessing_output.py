"""Fast I/O / preprocessing / output tests for inp2rad (P2 lane).

No Radioss solver is needed: every test calls a single converter helper with
a small in-memory deck or a temporary .inp file.
"""
import contextlib
import importlib.util
import io
import os
import tempfile
import unittest
from unittest import mock

MODULE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "inp2rad", "inp2rad.py",
)
spec = importlib.util.spec_from_file_location("inp2rad_under_test", MODULE_PATH)
inp2rad = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inp2rad)


class Inp2radIOTestCase(unittest.TestCase):
    """Restores global module state changed by the converter helpers."""

    def setUp(self):
        self._saved = {
            name: getattr(inp2rad, name)
            for name in ("or_gui", "run_timer", "debug_mode", "input_file_path", "input_file_name")
        }
        inp2rad.or_gui = False
        inp2rad.run_timer = False
        inp2rad.debug_mode = False
        inp2rad.input_file_path = ""
        inp2rad.input_file_name = ""
        inp2rad.display_names.clear()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

    def tearDown(self):
        for name, value in self._saved.items():
            setattr(inp2rad, name, value)

    def lines(self, *lines):
        return [line + "\n" for line in lines]

    def capture(self, function, *args, **kwargs):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            result = function(*args, **kwargs)
        return result, stream.getvalue()


class TestIncludes(Inp2radIOTestCase):

    def test_recursive_and_quoted_includes_are_expanded(self):
        base = self.temp_dir.name
        os.makedirs(os.path.join(base, "sub"))
        with open(os.path.join(base, "main.inp"), "w") as handle:
            handle.write("*INCLUDE, INPUT=\"sub/a.inp\"\n")
        with open(os.path.join(base, "sub", "a.inp"), "w") as handle:
            handle.write("*INCLUDE, INPUT=deep.inc\n*NODE\n")
        with open(os.path.join(base, "sub", "deep.inc"), "w") as handle:
            handle.write("7, 1.0, 2.0, 3.0\n")
        expanded, _, _, _, _, _, _ = inp2rad.input_read(os.path.join(base, "main.inp"))
        self.assertIn("7, 1.0, 2.0, 3.0\n", expanded)

    def test_missing_include_is_flagged_and_not_left_as_literal_card(self):
        base = self.temp_dir.name
        with open(os.path.join(base, "main.inp"), "w") as handle:
            handle.write("*INCLUDE, INPUT=missing.inp\n*NODE\n")
        (expanded, _, _, _, _, _, _), output = self.capture(
            inp2rad.input_read, os.path.join(base, "main.inp")
        )
        self.assertFalse(any(line.strip().startswith("*INCLUDE") for line in expanded))
        self.assertTrue(any("contents ignored" in line for line in expanded))
        self.assertIn("NOT converted", output)

    def test_include_cycle_is_skipped(self):
        base = self.temp_dir.name
        with open(os.path.join(base, "a.inp"), "w") as handle:
            handle.write("*INCLUDE, INPUT=a.inp\n*NODE\n1,0,0,0\n")
        with open(os.path.join(base, "a.inp")) as handle:
            deck = handle.readlines()
        expanded, output = self.capture(inp2rad.expand_includes, deck, base)
        self.assertIn("cycle", output)
        self.assertTrue(any("1,0,0,0" in line for line in expanded))


class TestPreprocessing(Inp2radIOTestCase):

    def test_quoted_names_and_system_parameters_are_preserved(self):
        lines = self.lines(
            '*ELSET, ELSET="part (left)"',
            "*SYSTEM, TYPE=CYLINDRICAL, ID=9, NSET=SYSNODES",
            "0.,0.,0.,0.,0.,1.",
        )
        result = inp2rad.preprocess_lines(lines)
        # quoted names are sanitized internally so every .inp parser in the
        # converter sees the same character set; the original is a display name
        self.assertIn("part _left_", result[0])
        self.assertEqual(inp2rad.display_name("part _left_"), "part (left)")
        self.assertIn("TYPE=CYLINDRICAL", result[1])
        self.assertIn("NSET=SYSNODES", result[1])
        self.assertIn("ID=1", result[1])

    def test_debug_write_is_silent_when_debug_mode_off(self):
        old_cwd = os.getcwd()
        os.chdir(self.temp_dir.name)
        try:
            inp2rad.debug_write(["*NODE\n"], "_test_gate.inp")
        finally:
            os.chdir(old_cwd)
        self.assertFalse(os.path.exists(
            os.path.join(self.temp_dir.name, "inp2rad_test_gate.inp")
        ))

    def test_assembly_raises_catchable_error_in_gui_mode(self):
        inp2rad.or_gui = True
        with self.assertRaises(ValueError):
            inp2rad.preprocess_lines(self.lines("*ASSEMBLY"))

    def test_expand_generate_without_data_warns_instead_of_crashing(self):
        result, output = self.capture(
            inp2rad.expand_elset_ranges, self.lines("*ELSET, ELSET=A, GENERATE")
        )
        self.assertEqual(result[0].strip(), "*ELSET, ELSET=A")
        self.assertIn("no range data", output)

    def test_debug_dump_uses_safe_path_without_input_globals(self):
        old_cwd = os.getcwd()
        os.chdir(self.temp_dir.name)
        inp2rad.debug_mode = True
        try:
            self.capture(inp2rad.expand_elset_ranges, self.lines("*NODE"))
        finally:
            os.chdir(old_cwd)
        self.assertTrue(os.path.exists(
            os.path.join(self.temp_dir.name, "inp2rad_test_expanded.inp")
        ))


class TestTransformsAndNodes(Inp2radIOTestCase):

    def test_transform_fallback_uses_sixth_coordinate(self):
        lines = self.lines("*SYSTEM, ID=3", "0.,0.,0.,1.,2.,3.", "*NODE")
        transform_lines, transform_data = inp2rad.convert_transforms(lines)
        self.assertEqual(transform_data, ["3"])
        self.assertIn("3.00000000", transform_lines[-2])

    def test_non_rectangular_system_is_converted_with_warning(self):
        lines = self.lines(
            "*SYSTEM, ID=2, TYPE=CYLINDRICAL",
            "0.,0.,0.,0.,0.,1.",
            "1.,0.,0.",
        )
        _, output = self.capture(inp2rad.convert_transforms, lines)
        self.assertIn("approximated", output)

    def test_read_nodes_resets_transform_between_blocks(self):
        lines = self.lines(
            "*SYSTEM, ID=7",
            "0.,0.,0.,1.,0.,0.",
            "*NODE",
            "1,0,0,0",
            "*ELEMENT, TYPE=C3D4, ELSET=E",
            "1,1,2,3,4",
            "*NODE",
            "2,1,1,1",
        )
        node_data, _ = inp2rad.read_nodes(lines)
        self.assertEqual(sorted(node_data), ["0", "7"])
        self.assertEqual(len(node_data["7"]), 1)
        self.assertEqual(len(node_data["0"]), 1)


class TestEngineOutput(Inp2radIOTestCase):

    def test_missing_runtime_data_line_warns_and_uses_defaults(self):
        engine, output = self.capture(
            inp2rad.parse_control_data, self.lines("*DYNAMIC, EXPLICIT"), "run"
        )
        self.assertIn("no time data line", output)
        engine_text = "".join(engine)
        self.assertIn("/RUN/run/1", engine_text)
        self.assertIn("Time history for run", engine_text)

    def test_field_output_selection_filters_anim_cards(self):
        deck = self.lines(
            "*DYNAMIC, EXPLICIT",
            "0.01, 1.0",
            "*OUTPUT, FIELD",
            "U, V",
        )
        engine, output = self.capture(inp2rad.parse_control_data, deck, "run")
        engine_text = "".join(engine)
        self.assertIn("/ANIM/VECT/DISP", engine_text)
        self.assertNotIn("/ANIM/BRICK/TENS/STRESS", engine_text)
        self.assertNotIn("/ANIM/ELEM/ENER", engine_text)
        # cards marked '*' must survive an explicit variable list
        self.assertIn("/ANIM/NODA/DT", engine_text)
        self.assertIn("/ANIM/NODA/DMAS", engine_text)
        self.assertNotIn("was not converted", output)

    def test_unknown_field_variable_warns(self):
        deck = self.lines("*OUTPUT, FIELD", "U, NOPE")
        _, output = self.capture(inp2rad.parse_control_data, deck, "run")
        self.assertIn("NOPE", output)

    def test_history_interval_and_unconverted_request_warning(self):
        deck = self.lines("*OUTPUT, HISTORY, TIME INTERVAL=0.005", "U, RF")
        engine, output = self.capture(inp2rad.parse_control_data, deck, "run")
        self.assertIn("history output request", output)
        self.assertIn("0.005", "".join(engine))

    def test_th_title_has_title_line(self):
        engine = inp2rad.parse_control_data([], "my_model")
        self.assertEqual(engine[-1], "Time history for my_model\n")


class TestPartAndRigidElsets(Inp2radIOTestCase):

    def _placeholder_deck(self, kind="part"):
        name = "placeholder_elset_" if kind == "part" else "placeholder_rigidelset_"
        return self.lines(
            f"*ELEMENT, TYPE=C3D4, ELSET={name}1",
            "20,2,3,4,5",
            "30,3,4,5,6",
            "10,1,2,3,4",
            "*ELSET, ELSET=SET_B",
            "20",
            "*ELSET, ELSET=SET_A",
            "30, 10",
            "*SOLID SECTION, ELSET=SET_A, MATERIAL=M",
            "*SOLID SECTION, ELSET=SET_B, MATERIAL=M",
        )

    def test_part_blocks_flush_at_eof_in_element_order(self):
        deck = inp2rad.preprocess_lines(self._placeholder_deck())
        output = inp2rad.create_part_elsets(deck)
        text = "".join(output)
        self.assertIn("*ELEMENT,TYPE=C3D4,ELSET=SET_B\n20, 2, 3, 4, 5", text)
        set_a_block = text.split("*ELEMENT,TYPE=C3D4,ELSET=SET_A\n", 1)[1]
        self.assertIn("10, 1, 2, 3, 4", set_a_block)
        self.assertLess(set_a_block.index("10, 1, 2, 3, 4"),
                        set_a_block.index("30, 3, 4, 5, 6"))
        # consecutive *ELSET cards survived the replacement
        self.assertIn("*ELSET, ELSET=SET_B", text)
        self.assertIn("*ELSET, ELSET=SET_A", text)

    def test_rigid_blocks_flush_at_eof(self):
        deck = inp2rad.preprocess_lines(self._placeholder_deck("rigid"))
        # rigid elsets are collected from *RIGID BODY cards
        deck = [line.replace("*SOLID SECTION", "*RIGID BODY") for line in deck]
        output = inp2rad.create_rigid_elsets(deck, {})
        text = "".join(output)
        self.assertIn("*ELEMENT,TYPE=C3D4,ELSET=SET_A", text)
        self.assertIn("*ELSET, ELSET=SET_B", text)

    def test_elset_cycle_detection_warns(self):
        deck = self.lines(
            "*ELSET, ELSET=A", "B",
            "*ELSET, ELSET=B", "A",
        )
        _, output = self.capture(inp2rad.find_referenced_elsets, deck)
        self.assertIn("Circular", output)


class TestPpmRigids(Inp2radIOTestCase):

    def test_only_rot_node_lines_are_rewritten(self):
        deck = self.lines(
            "*RIGID BODY, REF NODE=100, ROT NODE=200",
            "*BOUNDARY",
            "200, 1, 3, 0.0",
            "ALLNODES, ENCASTRE",
            "*CLOAD",
            "200, 2, 10.0",
            "OTHER, 1, 5.0",
        )
        output = inp2rad.ppm_rigids(deck)
        self.assertIn("100, 4, 6, 0.0\n", output)
        self.assertIn("ALLNODES, ENCASTRE\n", output)
        self.assertIn("100, 5, 10.0\n", output)
        self.assertIn("OTHER, 1, 5.0\n", output)

    def test_non_numeric_dofs_leave_line_unchanged(self):
        deck = self.lines(
            "*RIGID BODY, REF NODE=100, ROT NODE=200",
            "*BOUNDARY",
            "200, ENCASTRE",
        )
        _, output = self.capture(inp2rad.ppm_rigids, deck)
        self.assertIn("non-numeric DOFs", output)
        self.assertIn("200, ENCASTRE\n", inp2rad.ppm_rigids(deck))


class TestOutputPaths(Inp2radIOTestCase):

    def test_output_directory_and_prefix_are_honoured(self):
        base = self.temp_dir.name
        with open(os.path.join(base, "deck.inp"), "w") as handle:
            handle.write("*NODE\n1,0,0,0\n")
        out_dir = os.path.join(base, "results")
        result = inp2rad.input_read(
            os.path.join(base, "deck.inp"), output_dir=out_dir, output_prefix="custom"
        )
        self.assertEqual(result[1], "deck.inp")
        self.assertEqual(result[3], "custom_0000.rad")
        self.assertEqual(result[4], os.path.join(out_dir, "custom_0000.rad"))
        self.assertEqual(result[6], os.path.join(out_dir, "custom_0001.rad"))
        self.assertTrue(os.path.isdir(out_dir))


class TestEndToEndConversion(Inp2radIOTestCase):

    DECK = """*NODE
1,0,0,0
2,1,0,0
3,0,1,0
4,0,0,1
*ELEMENT, TYPE=C3D4, ELSET={elset}
1,1,2,3,4
*ELSET, ELSET={elset}
1
*MATERIAL, NAME=STEEL
*DENSITY
7.8e-9
*ELASTIC
210000, 0.3
*SOLID SECTION, ELSET={elset}, MATERIAL=STEEL
"""

    def convert(self, elset):
        base = self.temp_dir.name
        deck_path = os.path.join(base, "minimal.inp")
        with open(deck_path, "w") as handle:
            handle.write(self.DECK.format(elset=elset))
        with contextlib.redirect_stdout(io.StringIO()), mock.patch("builtins.input", return_value=""):
            success = inp2rad.start(deck_path)
        starter = os.path.join(base, "minimal_0000.rad")
        engine = os.path.join(base, "minimal_0001.rad")
        return success, starter, engine

    def test_minimal_solid_deck_converts_and_writes_rad_files(self):
        success, starter, engine = self.convert("SOLIDS")
        self.assertTrue(success)
        self.assertTrue(os.path.exists(starter))
        self.assertTrue(os.path.exists(engine))
        with open(starter) as handle:
            self.assertIn("/NODE", handle.read())

    def test_quoted_elset_deck_converts_and_keeps_display_name(self):
        success, starter, engine = self.convert('"part (left)"')
        self.assertTrue(success)
        self.assertTrue(os.path.exists(starter))
        self.assertTrue(os.path.exists(engine))
        with open(starter) as handle:
            starter_text = handle.read()
        self.assertIn("part (left)", starter_text)
        self.assertIn("/PART/", starter_text)

    def test_create_nblocks_tolerates_group_only_entries(self):
        blocks = inp2rad.create_nblocks({
            "NODESET": {"id": 1, "values": ["10"], "is_referenced": False},
            "GROUP_ONLY": {"id": 2},
        })
        self.assertEqual(len(blocks), 1)
        self.assertIn("/GRNOD/NODE/1", blocks[0][0])

    def test_degenerate_cylindrical_system_is_handled(self):
        deck = self.lines(
            "*SYSTEM, ID=4, TYPE=CYLINDRICAL",
            "0.,0.,0.,0.,0.,0.",  # zero-length axis
            "0.,0.,0.",           # zero-length X reference
        )
        (transform_lines, transform_data), output = self.capture(
            inp2rad.convert_transforms, deck
        )
        self.assertEqual(transform_data, ["4"])
        self.assertIn("zero-length axis", output)
        self.assertIn("fallback X direction", output)
        self.assertEqual(len(transform_lines), 11)


if __name__ == "__main__":
    unittest.main()
