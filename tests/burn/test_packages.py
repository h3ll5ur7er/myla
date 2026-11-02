"""Burn test: packages in both loaders (MYLA-92, D73 (6), Architecture/Project-tool).

A project with two packages, `geo` (a package root re-exporting through
relative imports, a nested directory) and `fmt` (importing `geo` by name), runs,
tests and builds alike with the self-hosted `build/myla`, `interp_main` and
`gen_main` (`… --package name=dir`), its tests printing what the Python CLI
printed; a nested file loaded with a project root resolves; and the module
errors packages bring (and errors inside a package's modules) print exactly as
the Python loader's.

The Python CLI's and loader's answers are recorded (`tests/burn/_golden.py`,
MYLA-219); the Python CLI no longer runs or builds the project alongside.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest

from ._golden import golden
from ._native import CAN_BUILD_NATIVE, SKIP_REASON
from ._tools import STDLIB_ROOT, selfhost_tool
from .test_selfhost_cli import _Layout

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))

# The packages, at <ws>/geo and <ws>/fmt (package directories; the loader gets
# their src/).
PACKAGES = {
    "geo/src/geo.my": "pub from .shapes import Circle, area\n"
                      "#test()[0]\n"
                      "pub fun origin() -> int {\n    return 0\n}\n",
    "geo/src/shapes.my": "from .units import scale\n"
                         "pub struct Circle { r: int }\n"
                         "#test(Circle { r: 1 })[30]\n"
                         "pub fun area(c: Circle) -> int {\n    return scale(3 * c.r * c.r)\n}\n",
    "geo/src/units.my": "pub fun scale(x: int) -> int {\n    return x * 10\n}\n",
    "geo/src/curves/round.my": "pub fun pi() -> int {\n    return 3\n}\n",
    "fmt/src/fmt.my": "from geo import Circle, area\n"
                      "pub fun show(c: Circle) -> str {\n"
                      "    return f\"circle of radius {c.r}, area {area(c)}\"\n}\n",
}

MAIN = """\
from geo import Circle, area
import geo.curves.round as round
import fmt
from .util import twice
from std.io import println

#test(3)[27]
fun circle_area(r: int) -> int {
    return area(Circle { r: r }) / twice(5)
}

fun main() {
    let c = Circle { r: 2 }
    println(fmt.show(c))
    print(area(c))
    print(round.pi())
    print(circle_area(3))
}
"""

PROJECT = {
    "app/main.my": MAIN,
    "app/util.my": "pub fun twice(x: int) -> int {\n    return x * 2\n}\n",
    # a nested entry, loaded with app2/src as its project root
    "app2/src/util.my": "pub fun two() -> int {\n    return 2\n}\n",
    "app2/src/nested/near.my": "pub fun one() -> int {\n    return 1\n}\n",
    "app2/src/nested/deep.my": "import util\nfrom .near import one\nimport geo\n"
                               "fun main() {\n    print(util.two() + one() + geo.origin())\n}\n",
}

EXPECTED_RUN = "circle of radius 2, area 120\n120\n3\n27\n"

FLAGS = ("geo={ws}/geo/src", "fmt={ws}/fmt/src")

# Rejected projects: (files under <ws>, --package values); `{ws}` is the
# workspace. The packages above are always there.
MODULE_ERRORS = {
    "shadowed_by_a_file": ({"app/main.my": "import geo\nfun main() {}\n", "app/geo.my": ""}, FLAGS),
    "shadowed_by_a_directory": ({"app/main.my": "fun main() {}\nfrom geo.shapes import Circle\n",
                                 "app/geo/x.my": ""}, FLAGS),
    "unresolved_in_a_package": ({"app/main.my": "import geo.nope\nfun main() {}\n"}, FLAGS),
    "unresolved_without_packages": ({"app/main.my": "import geo\nfun main() {}\n"}, ()),
    "no_root_module": ({"app/main.my": "import fmt\nfun main() {}\n"}, ("fmt={ws}/geo/src/curves",)),
    "ambiguous_in_a_package": ({"app/main.my": "import geo.units\nfun main() {}\n",
                                "geo/src/units/units.my": ""}, FLAGS),
    "private_name_in_a_package": ({"app/main.my": "from geo.units import secret\nfun main() {}\n"}, FLAGS),
    "type_error_in_a_package": ({"app/main.my": "import bad\nfun main() {\n    print(bad.f())\n}\n",
                                 "bad/src/bad.my": "pub fun f() -> int {\n    return \"s\"\n}\n"},
                                ("bad={ws}/bad/src",)),
    "parse_error_in_a_package_module": ({"app/main.my": "from geo import origin\nfun main() {}\n",
                                         "geo/src/geo.my": "from .shapes import area\n"
                                                           "pub fun origin() -> int {\n    return 1 +\n}\n"},
                                        FLAGS),
    "package_named_std": ({"app/main.my": "fun main() {}\n"}, ("std={ws}/geo/src",)),
    "given_twice": ({"app/main.my": "fun main() {}\n"}, ("geo={ws}/geo/src", "geo={ws}/fmt/src")),
    "invalid_name": ({"app/main.my": "fun main() {}\n"}, ("geo-x={ws}/geo/src",)),
    "keyword_name": ({"app/main.my": "fun main() {}\n"}, ("match={ws}/geo/src",)),
    "empty_name": ({"app/main.my": "fun main() {}\n"}, ("={ws}/geo/src",)),
    "malformed_flag": ({"app/main.my": "fun main() {}\n"}, ("geo",)),
    "missing_directory": ({"app/main.my": "fun main() {}\n"}, ("geo={ws}/nowhere",)),
    "empty_directory": ({"app/main.my": "fun main() {}\n"}, ("geo=",)),
}


def _write(root: str, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)


def _package_args(flags, ws: str) -> list[str]:
    out: list[str] = []
    for flag in flags:
        out += ["--package", flag.format(ws=ws)]
    return out


# The recorded answers are about a workspace (`{ws}`) holding the files given,
# written into a fresh temporary directory; `{ws}` stands for it in the
# arguments and the answers, so they hold no path of the machine that recorded
# them.

@golden("packages.python_cli")
def _recorded_python_cli(argv: list[str], files: dict[str, str]) -> tuple[str, str, int]:
    """(stdout, stderr, exit) of the retired Python CLI (`myla.py *argv`) run
    in a workspace holding `files`."""
    with tempfile.TemporaryDirectory() as ws:
        _write(ws, files)
        proc = subprocess.run([sys.executable, os.path.join(_REPO, "myla.py"),
                               *(a.replace("{ws}", ws) for a in argv)],
                              cwd=ws, capture_output=True, text=True)
        return proc.stdout.replace(ws, "{ws}"), proc.stderr.replace(ws, "{ws}"), proc.returncode


def _python_cli(argv: list[str], files: dict[str, str], ws: str) -> tuple[str, str, int]:
    """What the Python CLI printed for `argv` (see `_recorded_python_cli`), as
    if run in the workspace `ws`."""
    return tuple(a.replace("{ws}", ws) if isinstance(a, str) else a
                 for a in _recorded_python_cli(argv, files))


@golden("packages.python_diagnostic")
def _recorded_python_diagnostic(files: dict[str, str], flags: list[str]) -> str:
    """The Python loader's diagnostic for `{ws}/app/main.my` in a workspace
    holding `files`, with `flags`, rendered as the self-hosted tools print it
    (every file by the path it was loaded from)."""
    from myla.errors import MylaError
    from myla.loader import default_stdlib_root, link, parse_package_flag
    from myla.types import check

    with tempfile.TemporaryDirectory() as ws:
        _write(ws, files)
        entry = os.path.join(ws, "app", "main.my")
        try:
            packages = [parse_package_flag(f.format(ws=ws)) for f in flags]
            check(link(entry, stdlib_root=default_stdlib_root(), packages=packages))
        except MylaError as err:
            path = err.path or entry
            with open(path, encoding="utf-8") as fh:
                return err.render(fh.read(), path).replace(ws, "{ws}")
        raise AssertionError(f"{entry} was accepted")


def _python_diagnostic(files: dict[str, str], flags, ws: str) -> str:
    """The Python loader's diagnostic (see `_recorded_python_diagnostic`) for
    the workspace `ws`."""
    return _recorded_python_diagnostic(files, list(flags)).replace("{ws}", ws)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class PackageParity(_Layout):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.ws = os.path.join(cls._tmp.name, "ws")
        _write(cls.ws, PACKAGES)
        _write(cls.ws, PROJECT)
        cls.main = os.path.join(cls.ws, "app", "main.my")
        cls.flags = _package_args(FLAGS, cls.ws)
        cls.gen = selfhost_tool("gen_main")
        cls.interp = selfhost_tool("interp_main")

    def run_binary(self, path: str) -> tuple[str, str, int]:
        proc = subprocess.run([path], capture_output=True, text=True)
        return proc.stdout, proc.stderr, proc.returncode

    def test_run(self):
        my = self.myla_cmd("run", self.main, *self.flags)
        self.assertEqual((my.stdout, my.stderr, my.returncode), (EXPECTED_RUN, "", 0))
        my = self.myla_cmd("run", *self.flags, self.main)
        self.assertEqual(my.stdout, EXPECTED_RUN)
        it = subprocess.run([self.interp, self.main, STDLIB_ROOT, *self.flags], capture_output=True, text=True)
        self.assertEqual((it.stdout, it.stderr, it.returncode), (EXPECTED_RUN, "", 0))

    def test_test(self):
        # the entry file's own cases only, not the packages' (MYLA-187)
        my = self.myla_cmd("test", self.main, "--stdlib", STDLIB_ROOT, *self.flags)
        self.assertEqual(my.returncode, 0, my.stderr)
        self.assertIn("PASS  circle_area #1", my.stdout)
        for case in ("geo$geo$origin", "geo$shapes$area"):
            self.assertNotIn(case, my.stdout)
        py_out, py_err, py_code = _python_cli(["test", "{ws}/app/main.my", *_package_args(FLAGS, "{ws}")],
                                              {**PACKAGES, **PROJECT}, self.ws)
        self.assertEqual(py_code, 0, py_err)
        self.assertEqual(my.stdout, py_out)

    def test_build(self):
        out = os.path.join(self.ws, "out")
        os.makedirs(out, exist_ok=True)
        my = self.myla_cmd("build", self.main, *self.flags, "-o", os.path.join(out, "my"))
        self.assertEqual(my.returncode, 0, my.stderr)
        gen = subprocess.run([self.gen, self.main, STDLIB_ROOT, *self.flags], capture_output=True, text=True)
        self.assertEqual(gen.returncode, 0, gen.stderr)
        asm = os.path.join(out, "gen.s")
        with open(asm, "w", encoding="utf-8") as fh:
            fh.write(gen.stdout)
        subprocess.run(["as", "--64", "-o", asm + ".o", asm], check=True)
        subprocess.run(["ld", "-o", os.path.join(out, "gen"), asm + ".o"], check=True)
        for name in ("my", "gen"):
            with self.subTest(binary=name):
                self.assertEqual(self.run_binary(os.path.join(out, name)), (EXPECTED_RUN, "", 0))
        # package module ids carry the package's name, not its directory
        self.assertIn("geo$shapes$area", gen.stdout)
        self.assertNotIn("geo$src", gen.stdout)

    def test_project_root(self):
        entry = os.path.join(self.ws, "app2", "src", "nested", "deep.my")
        root = os.path.join(self.ws, "app2", "src")
        it = subprocess.run([self.interp, entry, STDLIB_ROOT, "--root", root, *self.flags],
                            capture_output=True, text=True)
        self.assertEqual((it.stdout, it.stderr, it.returncode), ("3\n", "", 0))
        # without the root, `import util` is looked up next to the file
        it = subprocess.run([self.interp, entry, STDLIB_ROOT, *self.flags], capture_output=True, text=True)
        self.assertEqual(it.returncode, 1)
        self.assertIn("cannot resolve import 'util'", it.stderr)

    def test_module_errors_match_the_python_loader(self):
        for name, (files, flags) in MODULE_ERRORS.items():
            with self.subTest(case=name):
                ws = os.path.join(self._tmp.name, "errors", name)
                _write(ws, PACKAGES)
                _write(ws, files)
                entry = os.path.join(ws, "app", "main.my")
                expected = _python_diagnostic({**PACKAGES, **files}, flags, ws)
                args = _package_args(flags, ws)
                gen = subprocess.run([self.gen, entry, STDLIB_ROOT, *args], capture_output=True, text=True)
                self.assertEqual((gen.stderr, gen.returncode), (expected + "\n", 1))
                my = self.myla_cmd("build", entry, *args, "-o", os.path.join(ws, "out"))
                self.assertEqual((my.stderr, my.returncode), (expected + "\n", 1))


if __name__ == "__main__":
    unittest.main()
