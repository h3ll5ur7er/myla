"""scripts/windows-runner.py's console driver (MYLA-708), the parts of it
that don't need Windows: what it runs a RUNNER_CASE with, the input it
types, and the Win32 records it hands to ctypes, laid out as on x86-64
Windows. The driver itself runs on CI's windows job only."""
from __future__ import annotations

import ctypes
import importlib.util
import os
import unittest

from .test_windows import RUNNER_CASES

_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir, "scripts", "windows-runner.py")
_spec = importlib.util.spec_from_file_location("windows_runner", _SCRIPT)
runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runner)

EXE = r"D:\a\myla\work\terminal-08\console.exe"


class ConsoleCommand(unittest.TestCase):
    def test_console_exe_is_named_by_its_path(self):
        # the first run on windows-latest: `cmd /c "console.exe ctrl …"`
        # gave the program `console.exe` as its argv[0], which it starts
        # again as a child; std.process looks for a bare name on PATH only
        # (D225), so the child wasn't found and the case ended at once with
        # exit 1 and nothing written (08, 09, 10)
        for rc in RUNNER_CASES:
            with self.subTest(case=rc["name"]):
                command = runner.console_command(rc, EXE, rc.get("host") == "pty")
                if rc.get("alone"):
                    self.assertEqual(command, [EXE, *rc["args"]])
                    continue
                self.assertTrue(command.startswith('cmd /c "'), command)
                self.assertIn(f'"{EXE}" {" ".join(rc["args"])} ', command)
                self.assertNotIn(" console.exe", command)

    def test_a_pseudo_consoles_streams_are_its_own(self):
        rc = {"args": ["readline"]}
        self.assertEqual(runner.console_command(rc, EXE, True), f'cmd /c ""{EXE}" readline < CON > out.txt 2> CON"')
        self.assertEqual(runner.console_command({"args": ["size"], "before": "mode con: cols=101 lines=33"}, EXE),
                         f'cmd /c "mode con: cols=101 lines=33 && "{EXE}" size > out.txt"')


class Typing(unittest.TestCase):
    def test_a_typed_ctrl_c_is_etx_on_a_pseudo_console(self):
        # (into a classic console's input buffer a Ctrl-C key is a key, no
        # CTRL_C_EVENT: 06's first run waited for "caught interrupt" for good)
        self.assertEqual(runner.vt_input(["Ctrl-c", "h", "i", "Enter"]), b"\x03hi\r")
        self.assertEqual(runner.vt_input(["Up", "Alt-x", "F5", "Delete", "Escape", "\u00f6"]),
                         b"\x1b[A\x1bx\x1b[15~\x1b[3~\x1b\xc3\xb6")

    def test_every_cases_keys_are_known(self):
        for rc in RUNNER_CASES:
            for st in rc["steps"]:
                for name in st.get("keys", []):
                    with self.subTest(case=rc["name"], key=name):
                        if rc.get("host") == "pty":
                            self.assertTrue(runner.vt_input([name]))
                        else:
                            down, up = runner.key_records(name)
                            self.assertEqual((down[0], up[0]), (1, 0))

    def test_the_pseudo_console_cases(self):
        # what a classic console can't give: a typed Ctrl-C, a close without
        # a window
        self.assertEqual(sorted(rc["args"][0] for rc in RUNNER_CASES if rc.get("host") == "pty"),
                         ["close", "readline"])


class Records(unittest.TestCase):
    """The Win32 structures as x86-64 Windows lays them out (fixed widths:
    a C long is 32 bits there, 64 here)."""

    def test_layouts(self):
        rec = runner.input_record_type()
        self.assertEqual((ctypes.sizeof(rec), rec.Event.offset), (20, 4))
        si = runner.startupinfoex_type()
        self.assertEqual((ctypes.sizeof(si), si.lpAttributeList.offset, si.hStdInput.offset), (112, 104, 80))
        self.assertEqual(ctypes.sizeof(runner.process_information_type()), 24)
        self.assertEqual(ctypes.sizeof(runner.COORD_type()), 4)


if __name__ == "__main__":
    unittest.main()
