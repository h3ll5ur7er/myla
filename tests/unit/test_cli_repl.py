"""`myla repl` in the Python CLI points to the REPL written in Myla (MYLA-82)."""
import contextlib
import io
import unittest

from myla.cli import main as cli_main


class TestReplPointer(unittest.TestCase):
    def test_points_to_the_self_hosted_repl(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = cli_main(["repl"])
        self.assertEqual(code, 2)
        self.assertIn("build/myla repl", err.getvalue())
        self.assertIn("scripts/bootstrap.sh", err.getvalue())


if __name__ == "__main__":
    unittest.main()
