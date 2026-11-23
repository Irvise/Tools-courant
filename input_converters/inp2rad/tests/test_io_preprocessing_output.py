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

    @staticmethod
    def fixed_coords(node_line):
        """Read the three 20-wide coordinate fields of a Radioss node line."""
        return [float(node_line[10 + 20 * i:30 + 20 * i]) for i in range(3)]


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
        # explicit IDs are preserved so /TRANSFORM and TH references still match
        self.assertIn("ID=9", result[1])

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
        (transform_lines, transform_data), output = self.capture(
            inp2rad.convert_transforms, lines
        )
        self.assertIn("converted to global XYZ", output)
        self.assertEqual(transform_data, ["2"])
        # identity frame: node coordinates are global, so no second transform
        points = transform_lines[-3:]
        self.assertEqual(points[0].split(), ["0.00000000"] * 3)
        self.assertEqual(points[1].split(), ["1.00000000", "0.00000000", "0.00000000"])
        self.assertEqual(points[2].split(), ["0.00000000", "1.00000000", "0.00000000"])

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
        (transform_lines, transform_data), _ = self.capture(
            inp2rad.convert_transforms, deck
        )
        self.assertEqual(transform_data, ["4"])
        self.assertEqual(len(transform_lines), 11)
        # Basis diagnostics are emitted once by collect_systems(), not from a
        # dead calculation in convert_transforms().
        _, basis_output = self.capture(inp2rad.collect_systems, deck)
        self.assertIn("zero-length axis", basis_output)
        self.assertIn("fallback X direction", basis_output)


class TestSystemIdsAndCurvedCoordinates(Inp2radIOTestCase):

    def test_explicit_ids_are_kept_and_only_missing_or_duplicate_ids_assigned(self):
        lines = self.lines(
            "*SYSTEM, ID=9, TYPE=CYLINDRICAL",
            "0,0,0,0,0,1",
            "*SYSTEM, TYPE=RECTANGULAR",
            "1,1,1,2,1,1",
            "*SYSTEM, ID=9",
            "0,0,0,1,0,0",
        )
        result, output = self.capture(inp2rad.preprocess_lines, lines)
        self.assertIn("ID=9", result[0])
        self.assertIn("ID=10", result[2])
        self.assertIn("ID=11", result[4])
        self.assertIn("duplicate *SYSTEM ID=9", output)

    def test_cylindrical_node_coordinates_are_converted_to_global(self):
        deck = self.lines(
            "*SYSTEM, ID=2, TYPE=CYLINDRICAL",
            "0,0,0,0,0,1",
            "1,0,0",
        )
        systems = inp2rad.collect_systems(deck)
        node_lines = inp2rad.convert_nodes({"2": ["1,2,90,3\n"]}, systems)
        values = self.fixed_coords(node_lines["2"][0])
        self.assertAlmostEqual(values[0], 0.0)
        self.assertAlmostEqual(values[1], 2.0)
        self.assertAlmostEqual(values[2], 3.0)

    def test_spherical_node_coordinates_are_converted_to_global(self):
        """Abaqus spherical data is (r, azimuth theta, polar phi)."""
        deck = self.lines(
            "*SYSTEM, ID=4, TYPE=SPHERICAL",
            "0,0,0,0,0,1",
            "1,0,0",
        )
        systems = inp2rad.collect_systems(deck)
        node_lines = inp2rad.convert_nodes(
            {"4": ["1,2,90,0\n", "2,2,0,90\n", "3,2,0,0\n"]}, systems
        )
        # theta=90, phi=0 -> +Z; theta=0, phi=90 -> +X; phi=0 -> +Z
        first = self.fixed_coords(node_lines["4"][0])
        second = self.fixed_coords(node_lines["4"][1])
        third = self.fixed_coords(node_lines["4"][2])
        self.assertAlmostEqual(first[0], 0.0)
        self.assertAlmostEqual(first[1], 0.0)
        self.assertAlmostEqual(first[2], 2.0)
        self.assertAlmostEqual(second[0], 2.0)
        self.assertAlmostEqual(second[1], 0.0)
        self.assertAlmostEqual(second[2], 0.0)
        self.assertAlmostEqual(third[2], 2.0)

    def test_rectangular_nodes_keep_their_local_coordinates(self):
        deck = self.lines("*SYSTEM, ID=1", "0,0,0,1,0,0")
        systems = inp2rad.collect_systems(deck)
        node_lines = inp2rad.convert_nodes({"1": ["7,1,2,3\n"]}, systems)
        self.assertEqual(self.fixed_coords(node_lines["1"][0]), [1.0, 2.0, 3.0])

    def test_system_ids_are_normalized_and_non_numeric_ids_replaced(self):
        lines = self.lines(
            "*SYSTEM, ID=01, TYPE=CYLINDRICAL",
            "0,0,0,0,0,1",
            "*SYSTEM, ID=SYS_A, TYPE=RECTANGULAR",
            "1,1,1,2,1,1",
        )
        result, output = self.capture(inp2rad.preprocess_lines, lines)
        self.assertIn("ID=1", result[0])
        self.assertNotIn("ID=01", result[0])
        # ID=SYS_A cannot be used in /TRANSFORM; it gets the next free number
        self.assertIn("ID=2", result[2])
        self.assertIn("non-numeric *SYSTEM ID=SYS_A", output)

        (transforms, transform_data), _ = self.capture(
            inp2rad.convert_transforms, result[:4]
        )
        self.assertIn("/TRANSFORM/POSITION/1", "".join(transforms))
        self.assertEqual(transform_data, ["1", "2"])

    def test_normalized_id_is_used_for_node_group_and_system_data(self):
        deck = self.lines("*SYSTEM, ID=03", "0,0,0,1,0,0", "*NODE", "1,1,2,3")
        node_data, _ = inp2rad.read_nodes(deck)
        self.assertIn("3", node_data)
        systems = inp2rad.collect_systems(deck)
        self.assertIn("3", systems)


class TestFieldVariableMapping(Inp2radIOTestCase):

    def test_extended_field_variables_map_to_radioss_anim_cards(self):
        deck = self.lines(
            "*OUTPUT, FIELD",
            "S, E, PE, TEMP, RF, STATUS, U1, S11",
        )
        engine, output = self.capture(inp2rad.parse_control_data, deck, "run")
        engine_text = "".join(engine)
        for card in (
            "/ANIM/BRICK/TENS/STRESS", "/ANIM/BRICK/TENS/STRAIN",
            "/ANIM/ELEM/EPSP", "/ANIM/NODA/TEMP", "/ANIM/ELEM/TEMP",
            "/ANIM/VECT/FREAC", "/ANIM/ELEM/OFF", "/ANIM/VECT/DISP",
            "/ANIM/SHELL/TENS/STRAIN/UPPER",
        ):
            self.assertIn(card, engine_text)
        self.assertNotIn("/ANIM/VECT/VEL", engine_text)
        self.assertNotIn("has no /ANIM equivalent", output)

    def test_no_variable_list_keeps_default_anim_set(self):
        engine = inp2rad.parse_control_data(self.lines("*OUTPUT, FIELD"), "run")
        engine_text = "".join(engine)
        self.assertIn("/ANIM/VECT/DISP", engine_text)
        self.assertIn("/ANIM/VECT/VEL", engine_text)
        self.assertIn("/ANIM/BRICK/TENS/STRAIN", engine_text)


class TestHistoryCards(Inp2radIOTestCase):

    def test_node_print_maps_to_th_node_variables(self):
        requests = inp2rad.collect_output_requests(
            self.lines("*NODE PRINT, NSET=OUTN", "U, RF")
        )
        nsets = {"OUTN": {"id": 1, "values": ["1", "2"], "is_referenced": False}}
        inp2rad.apply_node_output_requests(requests, nsets)
        blocks = inp2rad.create_nblocks(nsets)
        th_block = blocks[0][1]
        self.assertIn("/TH/NODE/1", th_block)
        self.assertIn("D         REACX     REACY     REACZ", th_block)
        self.assertTrue(requests['node'][0]['converted'])

    def test_element_print_maps_to_th_bric(self):
        requests = inp2rad.collect_output_requests(
            self.lines("*ELEMENT PRINT, ELSET=BULK", "S, PE")
        )
        blocks = inp2rad.create_history_blocks(
            requests, {"BULK": ["1", "2", "3"]}, [1, 3], [], [], [], first_id=5
        )
        text = "".join(blocks[0])
        self.assertIn("/TH/BRIC/5", text)
        self.assertIn("STRESS", text)
        self.assertIn("PLAS", text)
        self.assertIn("         1         3", text)
        self.assertTrue(requests['element'][0]['converted'])

    def test_shell_element_print_includes_skew_column(self):
        requests = inp2rad.collect_output_requests(
            self.lines("*ELEMENT PRINT, ELSET=SHELLS", "S")
        )
        blocks = inp2rad.create_history_blocks(
            requests, {"SHELLS": ["1", "2"]}, [], [1, 2], [], [], first_id=7
        )
        text = "".join(blocks[0])
        self.assertIn("/TH/SHEL/7", text)
        self.assertIn("STRESS", text)
        self.assertIn("         1         0", text)

    def test_contact_print_maps_to_th_inter(self):
        requests = inp2rad.collect_output_requests(
            self.lines("*CONTACT PRINT, INTERACTION=CONTACT_1", "CFORCE")
        )
        blocks = inp2rad.create_history_blocks(
            requests, contacts=["/INTER/TYPE24/7\nCONTACT_1\n"], first_id=2
        )
        text = "".join(blocks[0])
        self.assertIn("/TH/INTER/2", text)
        # FN/FT are valid /TH/INTER groups; bare FX/FY/FZ are not.
        for variable in ("FN", "FT", "CONTACT_1", "         7"):
            self.assertIn(variable, text)
        for invalid in ("FX", "FY", "FZ"):
            self.assertNotIn(invalid, text)
        self.assertTrue(requests['contact'][0]['converted'])

    def test_contact_print_default_uses_valid_def_group(self):
        requests = inp2rad.collect_output_requests(
            self.lines("*CONTACT PRINT, INTERACTION=CONTACT_1")
        )
        blocks = inp2rad.create_history_blocks(
            requests, contacts=["/INTER/TYPE24/7\nCONTACT_1\n"]
        )
        self.assertIn("DEF", "".join(blocks[0]))

    def test_contact_absolute_force_alias_uses_valid_group(self):
        requests = inp2rad.collect_output_requests(
            self.lines("*CONTACT PRINT, INTERACTION=CONTACT_1", "FX")
        )
        blocks = inp2rad.create_history_blocks(
            requests, contacts=["/INTER/TYPE24/7\nCONTACT_1\n"]
        )
        self.assertIn("|F|", "".join(blocks[0]))

    def test_unresolvable_request_is_still_warned_and_commented(self):
        deck = self.lines("*ELEMENT PRINT, ELSET=MISSING", "S")
        requests = inp2rad.collect_output_requests(deck)
        blocks = inp2rad.create_history_blocks(requests, {}, [], [], [], [])
        self.assertEqual(blocks, [])
        engine, output = self.capture(
            inp2rad.parse_control_data, deck, "run", output_requests=requests
        )
        self.assertIn("element output request(s) were not converted", output)
        self.assertIn("*ELEMENT PRINT, ELSET=MISSING", "".join(engine))

    def test_converted_requests_are_not_reported_as_unconverted(self):
        deck = self.lines("*NODE PRINT, NSET=OUTN", "U")
        requests = inp2rad.collect_output_requests(deck)
        nsets = {"OUTN": {"id": 1, "values": ["1"], "is_referenced": False}}
        inp2rad.apply_node_output_requests(requests, nsets)
        engine, output = self.capture(
            inp2rad.parse_control_data, deck, "run", output_requests=requests
        )
        self.assertNotIn("output request(s) were not converted", output)
        self.assertNotIn("*NODE PRINT", "".join(engine))

    def test_unmapped_node_variables_do_not_create_or_flag_a_th_node_group(self):
        deck = self.lines("*NODE PRINT, NSET=OUTN", "NOPE")
        requests = inp2rad.collect_output_requests(deck)
        nsets = {"OUTN": {"id": 1, "values": ["1"], "is_referenced": True}}
        _, output = self.capture(inp2rad.apply_node_output_requests, requests, nsets)
        self.assertFalse(nsets["OUTN"]["is_referenced"])
        self.assertEqual(inp2rad.create_nblocks(nsets)[0][1], "")
        self.assertIn("NOPE", output)
        self.assertFalse(requests['node'][0]['converted'])

    def test_unmapped_request_does_not_clobber_mapped_request_on_same_nset(self):
        deck = self.lines(
            "*NODE PRINT, NSET=OUTN", "U",
            "*NODE PRINT, NSET=OUTN", "NOPE",
        )
        requests = inp2rad.collect_output_requests(deck)
        nsets = {"OUTN": {"id": 1, "values": ["1"], "is_referenced": True}}
        _, output = self.capture(inp2rad.apply_node_output_requests, requests, nsets)
        # The mapped request still produces a /TH/NODE group with its variable.
        self.assertTrue(nsets["OUTN"]["is_referenced"])
        th_block = inp2rad.create_nblocks(nsets)[0][1]
        self.assertIn("/TH/NODE/1", th_block)
        self.assertIn("D         ", th_block)
        self.assertTrue(requests['node'][0]['converted'])
        self.assertFalse(requests['node'][1]['converted'])
        self.assertIn("NOPE", output)

    def test_shell_temp_is_dropped_with_warning(self):
        requests = inp2rad.collect_output_requests(
            self.lines("*ELEMENT PRINT, ELSET=SHELLS", "S, TEMP")
        )
        blocks, output = self.capture(
            inp2rad.create_history_blocks,
            requests, {"SHELLS": ["1"]}, [], [1], [], [],
        )
        text = "".join(blocks[0])
        self.assertIn("/TH/SHEL/", text)
        self.assertIn("STRESS", text)
        self.assertNotIn("TEMP", text)
        self.assertIn("TEMP", output)
        self.assertIn("/TH/SHEL equivalent", output)

    def test_brick_strain_e13_uses_epszx(self):
        self.assertEqual(inp2rad.BRICK_TH_VARIABLES['E13'], ('EPSZX',))
        requests = inp2rad.collect_output_requests(
            self.lines("*ELEMENT PRINT, ELSET=BULK", "E13")
        )
        blocks = inp2rad.create_history_blocks(
            requests, {"BULK": ["1"]}, [1], [], [], []
        )
        self.assertIn("EPSZX", "".join(blocks[0]))
        self.assertNotIn("EPSXZ", "".join(blocks[0]))


class TestEndToEndHistoryOutput(Inp2radIOTestCase):

    DECK = """*NODE
1,0,0,0
2,1,0,0
3,0,1,0
4,0,0,1
*ELEMENT, TYPE=C3D4, ELSET=SOLIDS
1,1,2,3,4
*ELSET, ELSET=SOLIDS
1
*NSET, NSET=OUTN
1,2
*MATERIAL, NAME=STEEL
*DENSITY
7.8e-9
*ELASTIC
210000, 0.3
*SOLID SECTION, ELSET=SOLIDS, MATERIAL=STEEL
*OUTPUT, FIELD
S, PE
*NODE PRINT, NSET=OUTN
U, RF
*ELEMENT PRINT, ELSET=SOLIDS
S, PE
"""

    def test_output_requests_reach_starter_and_leave_no_engine_warning(self):
        base = self.temp_dir.name
        deck_path = os.path.join(base, "history.inp")
        with open(deck_path, "w") as handle:
            handle.write(self.DECK)
        with contextlib.redirect_stdout(io.StringIO()), mock.patch("builtins.input", return_value=""):
            success = inp2rad.start(deck_path)
        self.assertTrue(success)
        with open(os.path.join(base, "history_0000.rad")) as handle:
            starter = handle.read()
        with open(os.path.join(base, "history_0001.rad")) as handle:
            engine = handle.read()
        self.assertIn("/TH/NODE/1", starter)
        self.assertIn("/TH/BRIC/", starter)
        self.assertIn("/ANIM/BRICK/TENS/STRESS", engine)
        self.assertNotIn("output request(s) were not converted", engine)

    SHELL_DECK = """*NODE
1,0,0,0
2,1,0,0
3,0,1,0
*ELEMENT, TYPE=S3, ELSET=TRIS
1,1,2,3
*ELSET, ELSET=TRIS
1
*NSET, NSET=OUTN
1,2
*MATERIAL, NAME=STEEL
*DENSITY
7.8e-9
*ELASTIC
210000, 0.3
*SHELL SECTION, ELSET=TRIS, MATERIAL=STEEL
1.0
*OUTPUT, HISTORY, NSET=OUTN, ELSET=TRIS
U, S
"""

    def test_history_request_with_nset_and_elset_writes_node_and_sh3n_groups(self):
        base = self.temp_dir.name
        deck_path = os.path.join(base, "shell.inp")
        with open(deck_path, "w") as handle:
            handle.write(self.SHELL_DECK)
        log = io.StringIO()
        with contextlib.redirect_stdout(log), mock.patch("builtins.input", return_value=""):
            success = inp2rad.start(deck_path)
        self.assertTrue(success)
        with open(os.path.join(base, "shell_0000.rad")) as handle:
            starter = handle.read()
        with open(os.path.join(base, "shell_0001.rad")) as handle:
            engine = handle.read()
        self.assertIn("/TH/NODE/1", starter)
        self.assertIn("/TH/SH3N/", starter)
        self.assertIn("STRESS", starter)
        self.assertNotIn("output request(s) were not converted", engine)
        # Variables without an equivalent for a group are warned and dropped.
        self.assertIn("have no /TH/SH3N equivalent", log.getvalue())


if __name__ == "__main__":
    unittest.main()
