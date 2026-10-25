"""Unit tests for the language server's compiler adapter (no pygls needed)."""
import os
import tempfile
import unittest

from myla.lsp.compiler_adapter import check_file, diagnostics_by_file


def _project(files: dict[str, str]) -> str:
    root = tempfile.mkdtemp(prefix="myla_lsp_")
    for rel, src in files.items():
        with open(os.path.join(root, rel), "w", encoding="utf-8") as fh:
            fh.write(src)
    return root


MAIN = "from .bad import f\nfun main() {\n    print(f())\n}\n"
BAD = "// one\n// two\npub fun f() -> int {\n    return \"oops\"\n}\n"


class TestDiagnosticFiles(unittest.TestCase):
    """MYLA-10: a diagnostic belongs to the file the error is in."""

    def test_an_error_in_an_imported_module_belongs_to_that_module(self):
        root = _project({"main.my": MAIN, "bad.my": BAD})
        main = os.path.join(root, "main.my")
        [d] = check_file(main, MAIN)
        self.assertEqual(d.path, os.path.realpath(os.path.join(root, "bad.my")))
        self.assertEqual((d.range.start_line, d.range.start_col), (3, 4))   # 0-based

    def test_unsaved_text_of_other_open_modules_is_used(self):
        root = _project({"main.my": MAIN, "bad.my": BAD})
        bad = os.path.join(root, "bad.my")
        fixed = "pub fun f() -> int {\n    return 1\n}\n"
        self.assertEqual(check_file(os.path.join(root, "main.my"), MAIN, {bad: fixed}), [])

    def test_an_error_in_the_checked_file_belongs_to_it(self):
        root = _project({"main.my": "fun main() {\n    let x: int = \"s\"\n}\n"})
        main = os.path.join(root, "main.my")
        [d] = check_file(main, None)
        self.assertEqual(d.path, os.path.realpath(main))

    def test_grouping_by_file_always_includes_the_checked_file(self):
        root = _project({"main.my": MAIN, "bad.my": BAD})
        main = os.path.join(root, "main.my")
        groups = diagnostics_by_file(main, check_file(main, MAIN))
        self.assertEqual(groups[os.path.realpath(main)], [])
        self.assertEqual(len(groups[os.path.realpath(os.path.join(root, "bad.my"))]), 1)


if __name__ == "__main__":
    unittest.main()
