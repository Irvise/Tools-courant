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
"""Shared helpers for the inp2rad contacts test suite.

The converter is a single large module that reads module-level globals and
prints progress information to stdout.  These helpers pin those globals and
keep the test runner output clean, without a solver or any external tools.
"""
import contextlib
import io
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_CONVERTER_PARENT = os.path.dirname(_HERE)
_CONVERTER_DIR = os.path.join(_CONVERTER_PARENT, "inp2rad")
for _path in (_HERE, _CONVERTER_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import inp2rad  # noqa: E402


def lines(text):
    """Split a triple-quoted inp snippet into newline-terminated lines."""
    return text.lstrip("\n").splitlines(keepends=True)


def joined(blocks):
    """Flatten a list of string blocks/lists into a single text blob."""
    out = []
    for block in blocks:
        if isinstance(block, str):
            out.append(block)
        else:
            out.extend(block)
    return "\n".join(out)


class ConverterTestCase(unittest.TestCase):
    """Base case pinning globals and silencing converter chatter."""

    def setUp(self):
        self.saved_globals = {
            name: getattr(inp2rad, name)
            for name in ("or_gui", "run_timer", "debug_mode", "radversion",
                         "e_magnitude", "rho_magnitude", "start_time")
        }
        inp2rad.or_gui = True
        inp2rad.run_timer = False
        inp2rad.debug_mode = False
        inp2rad.radversion = 2025
        inp2rad.e_magnitude = 10.0
        inp2rad.rho_magnitude = 1e-9
        inp2rad.start_time = 0
        self._stdout = io.StringIO()
        self._stdout_cm = contextlib.redirect_stdout(self._stdout)
        self._stdout_cm.__enter__()
        self.addCleanup(self._stdout_cm.__exit__, None, None, None)
        self.addCleanup(self._restore_globals)

    def _restore_globals(self):
        for name, value in self.saved_globals.items():
            setattr(inp2rad, name, value)

    @property
    def printed(self):
        return self._stdout.getvalue()


if __name__ == "__main__":
    unittest.main()
