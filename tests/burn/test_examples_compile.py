"""Burn test: every example, compiled natively, prints the same as the interpreter.

This is the core v0.0.3 guarantee — the x86-64 compiler and the tree-walking
interpreter agree on observable output.
"""
import os
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON, build_and_run, interpret

EXAMPLES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "examples")
)

EXAMPLES = [
    "hello.my", "variables.my", "functions.my", "loops.my",
    "control_flow.my", "structs.my", "attributes.my", "tuples.my", "enums.my",
    "types_and_aliases.my", "recursion.my", "regressions.my", "generics.my",
    "generic-types.my", "option-result.my", "operators.my", "constants.my",
    "lists.my", "maps.my", "strings.my",
]


class TestExamplesCompileCoverage(unittest.TestCase):
    """Platform-independent: the compile list must track the examples dir."""

    def test_compile_list_matches_examples(self):
        on_disk = {f for f in os.listdir(EXAMPLES_DIR) if f.endswith(".my")}
        listed = set(EXAMPLES)
        self.assertEqual(
            listed, on_disk,
            f"compile coverage out of sync: missing {sorted(on_disk - listed)}, "
            f"stale {sorted(listed - on_disk)}",
        )


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestExamplesCompile(unittest.TestCase):
    pass


def _make(name: str):
    def test(self):
        with open(os.path.join(EXAMPLES_DIR, name), encoding="utf-8") as fh:
            source = fh.read()
        native_out, code = build_and_run(source)
        self.assertEqual(code, 0, f"{name} exited with {code}")
        self.assertEqual(native_out, interpret(source))
    return test


for _name in EXAMPLES:
    setattr(TestExamplesCompile, f"test_{_name.replace('.', '_')}", _make(_name))


if __name__ == "__main__":
    unittest.main()
