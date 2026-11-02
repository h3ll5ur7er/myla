"""Burn test enforcing the project's `#test` convention for examples.

Convention (docs/Development/Conventions.md): every `.my` example must (a) have all of its embedded
`#test` cases pass, and (b) attach at least one `#test` to every value-returning
function. Entry points / void helpers are exempt (they cannot be unit-tested).

Once Myla is self-hosting, these in-language tests are the regression suite that
guards the compiler against breakage, so we keep them green from day one.
"""
import os
import re
import subprocess
import unittest

from tests.burn._tools import STDLIB_ROOT, selfhost_tool

EXAMPLES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "examples")
)

# a top-level function declaration: at the start of a line, maybe async
_FUN = re.compile(r"^(async\s+)?fun\s+(\w+)")


def _example_files() -> list[str]:
    return sorted(f for f in os.listdir(EXAMPLES_DIR) if f.endswith(".my"))


def _functions(source: str) -> list[dict]:
    """The top-level functions of `source`, found by a scan of its text (the
    examples are formatted consistently: top-level declarations start in the
    first column, their attributes on the lines right above them): for each,
    its name, whether it is async, generic or returns a value, and whether a
    `#test` is attached."""
    lines = source.splitlines()
    found = []
    for i, line in enumerate(lines):
        m = _FUN.match(line)
        if not m:
            continue
        # the signature runs from the name to the parameter list's closing
        # parenthesis; a return type follows it before the body's `{`
        rest = "\n".join(lines[i:])[m.end():]
        generic = rest.startswith("<")
        depth, pos = 0, rest.index("(")
        while True:
            depth += {"(": 1, ")": -1}.get(rest[pos], 0)
            pos += 1
            if depth == 0:
                break
        returns = rest[pos:rest.index("{", pos)].strip().startswith("->")
        # attributes sit on the lines above, maybe among comments and blanks
        tested = False
        for above in reversed(lines[:i]):
            above = above.strip()
            if above.startswith("#test"):
                tested = True
            elif not (above.startswith("#") or above.startswith("//") or above == ""):
                break
        found.append({"name": m.group(2), "async": bool(m.group(1)), "generic": generic,
                      "returns": returns, "tested": tested})
    return found


def _run_tests(name: str) -> tuple[str, str, int]:
    """(stdout, stderr, exit) of the self-hosted `myla test` on an example."""
    proc = subprocess.run([selfhost_tool("main"), "test", name, "--stdlib", STDLIB_ROOT],
                          capture_output=True, text=True, cwd=EXAMPLES_DIR)
    return proc.stdout, proc.stderr, proc.returncode


class TestExamplesTestSuite(unittest.TestCase):
    def test_there_are_examples(self):
        self.assertTrue(_example_files(), "no example .my files found")

    def test_every_value_returning_function_is_tested(self):
        seen = 0
        for name in _example_files():
            with open(os.path.join(EXAMPLES_DIR, name), encoding="utf-8") as fh:
                functions = _functions(fh.read())
            seen += len(functions)
            for fn in functions:
                if not fn["returns"]:
                    continue
                # Generic functions have no single concrete instantiation, so
                # they can't carry a `#test`; they are covered through tested
                # concrete wrappers instead.
                if fn["generic"]:
                    continue
                # `#test` can't run an async function (D89); its example's
                # output covers it
                if fn["async"]:
                    continue
                self.assertTrue(
                    fn["tested"],
                    f"{name}: function '{fn['name']}' returns a value but has "
                    f"no #test case (project convention requires one)",
                )
        self.assertGreater(seen, 0, "the scan found no top-level functions in the examples")

    def test_all_embedded_tests_pass(self):
        total = 0
        for name in _example_files():
            out, err, code = _run_tests(name)
            # one `PASS  f #1` or `FAIL  f #1: detail` line per case
            cases = [line for line in out.splitlines() if line.startswith(("PASS ", "FAIL "))]
            total += len(cases)
            for line in cases:
                self.assertTrue(line.startswith("PASS "), f"{name}: {line[6:]}")
            self.assertEqual((err, code), ("", 0), f"{name}: myla test failed:\n{out}{err}")
        self.assertGreater(total, 0, "expected at least one #test across the examples")


if __name__ == "__main__":
    unittest.main()
