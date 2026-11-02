"""`#test` coverage of the self-hosted compiler, softly enforced (D109,
MYLA-184): the share of value-returning functions in `selfhost/` with cases is
reported per module and overall; below 80 % the test warns (in its output and,
in CI, as a GitHub annotation) without failing."""

import os
import sys
import unittest
import warnings

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_REPO, "scripts"))

import test_coverage  # noqa: E402


class TestSelfhostCoverage(unittest.TestCase):
    def test_counts(self):
        # the counter itself: functions and methods with a result count, a
        # function counts as tested with one case
        import tempfile
        src = ("#test(1)[1]\nfun a(x: int) -> int {\n    return x\n}\n"
               "fun b(x: int) -> int {\n    return x\n}\n"
               "fun c() {\n    return\n}\n"
               "struct S {\n    n: int,\n}\n"
               "impl S {\n    #test(S { n: 1 })[1]\n    fun get(self) -> int {\n        return self.n\n    }\n"
               "    fun put(var self, n: int) {\n        self.n = n\n    }\n}\n")
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "m.my"), "w", encoding="utf-8") as fh:
                fh.write(src)
            self.assertEqual(test_coverage.coverage(tmp), [("m.my", 2, 3)])

    def test_selfhost_coverage(self):
        rows = test_coverage.coverage(os.path.join(_REPO, "selfhost"))
        share = test_coverage.overall(rows)
        print("\n" + test_coverage.report(rows), file=sys.stderr)
        if share < test_coverage.TARGET:
            msg = (f"#test coverage of selfhost/ is {share:.0%}, below the target of "
                   f"{test_coverage.TARGET:.0%} (D109)")
            if os.environ.get("GITHUB_ACTIONS"):
                print(f"::warning::{msg}", file=sys.stderr)
            warnings.warn(msg)


if __name__ == "__main__":
    unittest.main()
