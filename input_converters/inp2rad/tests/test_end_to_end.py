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
"""Fast end-to-end conversion test for the contacts/constraints topic."""
import os
import tempfile
from unittest import mock

from support import ConverterTestCase, inp2rad

DECK = """
*NODE, NSET=AllNodes
1, 0.0, 0.0, 0.0
2, 1.0, 0.0, 0.0
3, 0.0, 1.0, 0.0
4, 1.0, 1.0, 0.0
5, 0.0, 0.0, 1.0
6, 1.0, 0.0, 1.0
7, 0.0, 1.0, 1.0
8, 1.0, 1.0, 1.0
*NSET, NSET=Fixed
1, 2
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
*SURFACE INTERACTION, NAME=IntA
*FRICTION
0.2
*CONTACT PAIR, INTERACTION=IntA
Bottom, Top
*TIE, NAME=Tie1, TYPE=NODE TO SURFACE
Fixed, Top
*RIGID BODY, NSET=Fixed, REF NODE=1
*DYNAMIC, EXPLICIT
, 0.01
"""


class EndToEndContactDeckTests(ConverterTestCase):
    def test_start_writes_contact_tie_and_rigid_cards(self):
        with tempfile.TemporaryDirectory() as tmp:
            deck_path = os.path.join(tmp, "contacts.inp")
            with open(deck_path, "w") as deck_file:
                deck_file.write(DECK.lstrip("\n"))

            inp2rad.or_gui = False
            inp2rad.run_timer = False
            inp2rad.debug_mode = False
            with mock.patch("builtins.input", return_value=""):
                result = inp2rad.start(deck_path)

            self.assertTrue(result, self.printed)
            starter_path = os.path.join(tmp, "contacts_0000.rad")
            engine_path = os.path.join(tmp, "contacts_0001.rad")
            self.assertTrue(os.path.exists(starter_path))
            self.assertTrue(os.path.exists(engine_path))
            with open(starter_path) as starter:
                starter_text = starter.read()
            with open(engine_path) as engine:
                engine_text = engine.read()

        self.assertIn("/INTER/TYPE24/1", starter_text)   # *CONTACT PAIR
        self.assertIn("0.2", starter_text)               # friction coefficient
        self.assertIn("/INTER/TYPE2/", starter_text)     # *TIE
        self.assertIn("Tie1", starter_text)
        self.assertIn("/RBODY/", starter_text)           # *RIGID BODY
        self.assertIn("/RUN/contacts/1", engine_text)    # engine deck


if __name__ == "__main__":
    import unittest
    unittest.main()
