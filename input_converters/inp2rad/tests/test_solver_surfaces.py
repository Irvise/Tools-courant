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
"""Solver-gated contact-surface validation with the OpenCourant starter.

These tests are skipped unless the starter is available.  Override the
 defaults with the ``INP2RAD_STARTER`` / ``OPENCOURANT_PATH`` environment
 variables.  They exercise degraded S6/S8 shells, two-sided S2/beam faces and
 rough contacts and check that the generated deck is accepted by the starter.
"""
import os
import subprocess
import tempfile
import unittest
from unittest import mock

from support import ConverterTestCase, inp2rad

_ROOT = os.environ.get(
    "OPENCOURANT_PATH", "/home/fernando/Build/OpenCourant/OpenCourant")
_SOLVER = os.environ.get(
    "INP2RAD_STARTER",
    os.path.join(_ROOT, "exec", "starter_linux64_gf"))
_SOLVER_AVAILABLE = (
    os.path.isfile(_SOLVER) and os.access(_SOLVER, os.X_OK)
    and os.path.isdir(os.path.join(_ROOT, "hm_cfg_files")))


def _solver_env():
    env = os.environ.copy()
    env["RAD_CFG_PATH"] = os.path.join(_ROOT, "hm_cfg_files")
    env["RAD_H3D_PATH"] = os.path.join(
        _ROOT, "extlib", "h3d", "lib", "linux64")
    libs = [os.path.join(_ROOT, "extlib", "hm_reader", "linux64"),
            os.path.join(_ROOT, "extlib", "intelOneAPI_runtime", "linux64")]
    env["LD_LIBRARY_PATH"] = os.pathsep.join(
        libs + [env.get("LD_LIBRARY_PATH", "")])
    env["OMP_STACKSIZE"] = "400m"
    env["OMP_NUM_THREADS"] = "1"
    return env


DEGRADED_SHELL_DECK = """
*NODE
1, 0.0, 0.0, 0.0
2, 1.0, 0.0, 0.0
3, 0.0, 1.0, 0.0
4, 0.5, 0.0, 0.0
5, 0.5, 0.5, 0.0
6, 0.0, 0.5, 0.0
11, 2.0, 0.0, 0.0
12, 3.0, 0.0, 0.0
13, 3.0, 1.0, 0.0
14, 2.0, 1.0, 0.0
15, 2.5, 0.0, 0.0
16, 3.0, 0.5, 0.0
17, 2.5, 1.0, 0.0
18, 2.0, 0.5, 0.0
*ELSET, ELSET=S6Parts
1
*ELSET, ELSET=S8Parts
2
*MATERIAL, NAME=Steel
*DENSITY
7.85e-9
*ELASTIC
210000.0, 0.3
*SHELL SECTION, ELSET=S6Parts, MATERIAL=Steel
1.0
*SHELL SECTION, ELSET=S8Parts, MATERIAL=Steel
1.0
*ELEMENT, TYPE=S6, ELSET=S6Parts
1, 1, 2, 3, 4, 5, 6
*ELEMENT, TYPE=S8, ELSET=S8Parts
2, 11, 12, 13, 14, 15, 16, 17, 18
*SURFACE, NAME=SurfA, TYPE=ELEMENT
1, SPOS
*SURFACE, NAME=SurfB, TYPE=ELEMENT
2, SPOS
*SURFACE INTERACTION, NAME=FricA
*FRICTION
0.2
*CONTACT PAIR, INTERACTION=FricA
SurfA, SurfB
*DYNAMIC, EXPLICIT
, 0.001
"""

LINE_BEAM_DECK = """
*NODE
1, 0.0, 0.0, 0.0
2, 1.0, 0.0, 0.0
3, 0.0, 1.0, 0.0
4, 1.0, 1.0, 0.0
*ELSET, ELSET=Shells
1
*ELSET, ELSET=Beams
2, 3
*MATERIAL, NAME=Steel
*DENSITY
7.85e-9
*ELASTIC
210000.0, 0.3
*SHELL SECTION, ELSET=Shells, MATERIAL=Steel
1.0
*ELEMENT, TYPE=S4, ELSET=Shells
1, 1, 2, 4, 3
*ELEMENT, TYPE=S2, ELSET=Beams
2, 1, 2
*ELEMENT, TYPE=B31, ELSET=Beams
3, 3, 4
*SURFACE, NAME=SurfA, TYPE=ELEMENT
1, SPOS
*SURFACE, NAME=LineSurf, TYPE=ELEMENT
2, SPOS
*SURFACE, NAME=BeamSurf, TYPE=ELEMENT
3, SPOS
*SURFACE INTERACTION, NAME=FricA
*FRICTION
0.2
*CONTACT PAIR, INTERACTION=FricA
SurfA, LineSurf
*DYNAMIC, EXPLICIT
, 0.001
"""

ROUGH_DECK = """
*NODE
1, 0.0, 0.0, 0.0
2, 1.0, 0.0, 0.0
3, 0.0, 1.0, 0.0
4, 1.0, 1.0, 0.0
5, 0.0, 0.0, 1.0
6, 1.0, 0.0, 1.0
7, 0.0, 1.0, 1.0
8, 1.0, 1.0, 1.0
*ELSET, ELSET=Solids
1
*MATERIAL, NAME=Steel
*DENSITY
7.85e-9
*ELASTIC
210000.0, 0.3
*SOLID SECTION, ELSET=Solids, MATERIAL=Steel
*ELEMENT, TYPE=C3D8, ELSET=Solids
1, 1, 2, 4, 3, 5, 6, 8, 7
*SURFACE, NAME=Top, TYPE=ELEMENT
1, S1
*SURFACE, NAME=Bottom, TYPE=ELEMENT
1, S2
*SURFACE INTERACTION, NAME=RoughA
*FRICTION, ROUGH
*CONTACT PAIR, INTERACTION=RoughA
Bottom, Top
*DYNAMIC, EXPLICIT
, 0.001
"""


@unittest.skipUnless(
    _SOLVER_AVAILABLE,
    "OpenCourant starter / config tree is not available (set INP2RAD_STARTER "
    "and OPENCOURANT_PATH to enable solver-gated contact-surface tests)")
class SolverContactSurfaceTests(ConverterTestCase):
    """End-to-end conversion + starter runs (skipped when solver is absent)."""

    def _convert_and_run(self, name, deck):
        with tempfile.TemporaryDirectory() as tmp:
            inp_path = os.path.join(tmp, name + ".inp")
            with open(inp_path, "w") as handle:
                handle.write(deck.lstrip("\n"))

            inp2rad.or_gui = False
            inp2rad.run_timer = False
            inp2rad.debug_mode = False
            with mock.patch("builtins.input", return_value=""):
                self.assertTrue(inp2rad.start(inp_path), self.printed)

            rad_path = os.path.join(tmp, name + "_0000.rad")
            with open(rad_path) as handle:
                starter_text = handle.read()

            result = subprocess.run(
                [_SOLVER, "-i", os.path.basename(rad_path)],
                cwd=tmp, env=_solver_env(), stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, timeout=120)
            log = result.stdout.decode("utf-8", errors="replace")
        return starter_text, log, result.returncode

    def assert_solver_clean(self, log, returncode):
        self.assertEqual(returncode, 0, log[-4000:])
        self.assertIn("0 ERROR(S)", log)
        self.assertNotIn("ERROR TERMINATION", log)
        # An empty /SURF/SEG or a bad node group is a conversion error even
        # though the starter only warns about it.
        self.assertNotIn("WARNING IN SURFACE DEFINITION", log)
        self.assertNotIn("WARNING IN NODE GROUP DEFINITION", log)

    def test_degraded_shell_contact_surfaces_run_in_starter(self):
        starter_text, log, rc = self._convert_and_run(
            "degraded", DEGRADED_SHELL_DECK)
        self.assertIn("/SH3N/1", starter_text)     # S6 -> degraded tri shell
        self.assertIn("/SHELL/2", starter_text)    # S8 -> degraded quad shell
        self.assertIn("/INTER/TYPE24/1", starter_text)
        seg1 = starter_text.split("/SURF/SEG/1", 1)[1].split("#---", 1)[0]
        seg2 = starter_text.split("/SURF/SEG/2", 1)[1].split("#---", 1)[0]
        # Each block is: /SURF/SEG/id, title, then one line of segment nodes.
        self.assertEqual(len(seg1.strip().splitlines()[-1].split()), 3)
        self.assertEqual(len(seg2.strip().splitlines()[-1].split()), 4)
        self.assert_solver_clean(log, rc)

    def test_line_and_beam_faces_are_withheld_and_deck_runs(self):
        starter_text, log, rc = self._convert_and_run(
            "linebeam", LINE_BEAM_DECK)
        self.assertIn("two-node", self.printed)
        self.assertIn("no valid 3-D segments", self.printed)
        self.assertIn("interface skipped", self.printed)
        self.assertNotIn("/SURF/SEG/2", starter_text)
        self.assertNotIn("/SURF/SEG/3", starter_text)
        self.assertNotIn("/INTER/TYPE24/", starter_text)
        self.assert_solver_clean(log, rc)

    def test_rough_contact_deck_runs_in_starter(self):
        starter_text, log, rc = self._convert_and_run("rough", ROUGH_DECK)
        self.assertIn("ROUGH contact approximated", starter_text)
        self.assertIn("no true no-slip representation", self.printed)
        rows = starter_text.splitlines()
        idx = next(i for i, row in enumerate(rows)
                   if row.startswith("#              Stfac                Fric"))
        fric_card = next(row for row in rows[idx + 1:] if not row.startswith('#'))
        self.assertEqual(float(fric_card.split()[1]),
                         inp2rad.ROUGH_FRICTION_COEFF)
        self.assert_solver_clean(log, rc)


if __name__ == "__main__":
    unittest.main()
