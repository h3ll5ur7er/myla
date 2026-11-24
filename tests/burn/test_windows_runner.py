"""scripts/windows-runner.py's console driver (MYLA-708), the parts of it
that don't need Windows: what it runs a RUNNER_CASE with, the input it
types, and the Win32 records it hands to ctypes, laid out as on x86-64
Windows. The driver itself runs on CI's windows job only."""
from __future__ import annotations

import ctypes
import importlib.util
import os
import sys
import tempfile
import unittest

from ._native import EXE as EXE_SUFFIX, ON_WINDOWS
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


class Programs(unittest.TestCase):
    def test_a_word_without_a_slash_is_a_tool_on_path(self):
        # the debug cases run the machine's LLVM on a -g program (MYLA-757);
        # the other words are the bundle's programs or the case's own
        r = runner.Runner.__new__(runner.Runner)
        r.bundle = os.path.join(os.sep, "b")
        with tempfile.TemporaryDirectory() as d:
            # (on Windows a program on PATH is found by its extension, in
            # PATHEXT's case)
            tool = os.path.join(d, "llvm-symbolizer" + EXE_SUFFIX)
            with open(tool, "w") as fh:
                fh.write("#!/bin/sh\n")
            os.chmod(tool, 0o755)
            r.env = {"PATH": d}
            self.assertEqual(os.path.normcase(r.program("llvm-symbolizer", "/w")), os.path.normcase(tool))
        self.assertEqual(r.program("bin/debug.exe", "/w"), os.path.join(os.sep, "b", "bin", "debug.exe"))
        self.assertEqual(r.program("./hello.exe", "/w"), os.path.join("/w", "hello.exe"))


class BuildDirectory(unittest.TestCase):
    # `build OUT` empties OUT first: only a bundle it made before (its
    # cases.json) or an empty directory, never a checkout given by mistake
    def test_a_directory_that_isn_t_a_bundle_is_left_alone(self):
        with tempfile.TemporaryDirectory() as d:
            keep = os.path.join(d, "README.md")
            with open(keep, "w") as fh:
                fh.write("a checkout\n")
            with self.assertRaises(SystemExit) as e:
                runner.build(d, "myla", 1)
            self.assertIn("isn't a bundle", str(e.exception))
            self.assertTrue(os.path.exists(keep))

    def test_an_old_bundle_or_an_empty_directory_may_be_emptied(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(runner.may_empty(d))
            with open(os.path.join(d, "cases.json"), "w") as fh:
                fh.write("{}")
            self.assertTrue(runner.may_empty(d))
        self.assertTrue(runner.may_empty(os.path.join(os.sep, "no", "such", "dir")))


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
        # the commit charge's (MYLA-798)
        perf = runner.performance_information_type()
        self.assertEqual((ctypes.sizeof(perf), perf.PageSize.offset, perf.ProcessCount.offset), (104, 80, 92))
        counters = runner.process_memory_counters_type()
        self.assertEqual((ctypes.sizeof(counters), counters.PeakPagefileUsage.offset), (72, 64))


# A step's script and the command that runs it: sh's on Linux, Python's on
# Windows (MYLA-926: no sh there; the runner takes a word with no `/` for a
# program on PATH, a path such as Windows' sys.executable as it is)
SCRIPT = "t.py" if ON_WINDOWS else "t.sh"
RUN = [sys.executable, SCRIPT] if ON_WINDOWS else ["sh", SCRIPT]
# what each test's script does, in sh and in Python (its output bytes as
# they are: Python's text streams would end its lines with CR LF there)
TALLY_393 = ("echo 393; echo 'BAD child 7' >&2\n",
             "import sys\nsys.stdout.buffer.write(b'393\\n')\nsys.stderr.buffer.write(b'BAD child 7\\n')\n")
RIGHT_FIRST = ("if [ -e seen ]; then echo 1; else touch seen; echo 0; fi\n",
               "import os, sys\nif os.path.exists('seen'):\n    sys.stdout.buffer.write(b'1\\n')\n"
               "else:\n    open('seen', 'w').close()\n    sys.stdout.buffer.write(b'0\\n')\n")


class Reports(unittest.TestCase):
    """What a failed step says, and a tally's rate (MYLA-798: the report of
    process/many-children couldn't say why it failed)."""

    def runner_in(self, work: str, tally: bool = False):
        r = runner.Runner.__new__(runner.Runner)
        r.bundle, r.wine, r.runs, r.tally, r.env, r.note, r.tools_missing = work, [], 3, tally, dict(os.environ), "", []
        return r

    def script(self, work: str, body: tuple[str, str]) -> None:
        """The step's script, `body`'s sh or Python, as SCRIPT in `work`."""
        with open(os.path.join(work, SCRIPT), "w") as fh:
            fh.write(body[1] if ON_WINDOWS else body[0])

    def test_a_failed_step_shows_its_standard_error_checked_or_not(self):
        with tempfile.TemporaryDirectory() as d:
            self.script(d, TALLY_393)
            r = self.runner_in(d)
            bad = r.run_step(runner.step(RUN, "400\n", None), d, {})
            self.assertIn("stdout differs", bad)
            self.assertIn("its standard error b'BAD child 7\\n'", bad)
            self.assertEqual(r.run_step(runner.step(RUN, "393\n", None), d, {}), "")

    def test_a_tally_runs_every_run_and_gives_the_rate(self):
        with tempfile.TemporaryDirectory() as d:
            # right the first time, wrong after
            self.script(d, RIGHT_FIRST)
            case = {"name": "x/rate", "steps": [runner.step(RUN, "0\n", repeat=True)],
                    "files": {SCRIPT: SCRIPT}, "windows_only": ""}
            import contextlib
            import io
            said = io.StringIO()
            with contextlib.redirect_stdout(said):
                verdict, what = self.runner_in(d, tally=True).run_case(case)
            self.assertEqual(verdict, "FAIL")
            self.assertIn("2 runs failed", what)
            self.assertIn(f"rate x/rate step 1 ({' '.join(RUN)}): 1 of 3 right", said.getvalue())


if __name__ == "__main__":
    unittest.main()
