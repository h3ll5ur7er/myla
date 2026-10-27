"""Unit tests for the module loader / linker (v0.5.1b).

Each test writes a tiny multi-file project into a temp directory, links it, and
inspects the merged program (or runs it through the interpreter for behaviour).
"""
import contextlib
import io
import os
import tempfile
import unittest

from myla.cli import main as cli_main
from myla.errors import ModuleError, MylaError
from myla.interpreter import Interpreter
from myla.loader import link
from myla.types import check


def _project(files: dict[str, str]) -> str:
    """Materialize {relpath: source} under a fresh temp dir; return its path."""
    root = tempfile.mkdtemp(prefix="myla_mod_")
    for rel, src in files.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path) or root, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(src)
    return root


def run_project(files: dict[str, str], entry: str = "main.my") -> str:
    root = _project(files)
    checker = check(link(os.path.join(root, entry)))
    out = io.StringIO()
    Interpreter(checker, out).run()
    return out.getvalue()


def names(files: dict[str, str], entry: str = "main.my") -> list[str]:
    root = _project(files)
    prog = link(os.path.join(root, entry))
    return [getattr(d, "name", type(d).__name__) for d in prog.decls]


class TestLinking(unittest.TestCase):
    def test_from_import_function(self):
        out = run_project({
            "main.my": "from .lib import twice\n"
                       "fun main() { print(twice(21)) }\n",
            "lib.my": "pub fun twice(n: int32) -> int32 { return n + n }\n",
        })
        self.assertEqual(out, "42\n")

    def test_test_attributes_name_their_modules_declarations(self):
        # `#test` cases are expressions in the module's scope (MYLA-11)
        files = {
            "main.my": "from .lib import double\nfun main() { print(double(4)) }\n",
            "lib.my": ("pub const LIMIT: int = 10\n"
                       "struct P { x: int }\n"
                       "enum E { A(int), B }\n"
                       "fun val(e: E) -> int {\n"
                       "    return match e { A(n) => n, B => 0 }\n}\n"
                       "#test(LIMIT)[20]\n"
                       "#test(P { x: LIMIT }.x)[val(E.A(20))]\n"
                       "pub fun double(x: int) -> int {\n    return x * 2\n}\n"),
        }
        self.assertEqual(run_project(files), "8\n")
        checker = check(link(os.path.join(_project(files), "main.my")))
        results = Interpreter(checker, io.StringIO()).run_tests()
        self.assertEqual([(r.function, r.passed) for r in results], [("lib$double", True)] * 2)

    def test_entry_names_unqualified_imports_qualified(self):
        ns = names({
            "main.my": "from .lib import f\nfun main() { f() }\n",
            "lib.my": "pub fun f() {}\nfun helper() {}\n",
        })
        self.assertIn("main", ns)              # entry keeps simple names
        self.assertIn("lib$f", ns)
        self.assertIn("lib$helper", ns)        # private decls still qualified

    def test_cross_module_struct_and_field(self):
        out = run_project({
            "main.my": "from .geo import Point\n"
                       "fun main() {\n"
                       "    let p = Point { x: 2, y: 5 }\n"
                       "    print(p.x + p.y)\n"
                       "}\n",
            "geo.my": "pub struct Point { x: int32, y: int32 }\n",
        })
        self.assertEqual(out, "7\n")

    def test_cross_module_method_call(self):
        # Methods follow their type: importing the (pub) type makes its methods
        # callable; the impl lives in another module.
        out = run_project({
            "main.my": "from .geo import Point\n"
                       "fun main() {\n"
                       "    let p = Point { x: 3, y: 4 }\n"
                       "    print(p.norm2())\n"
                       "}\n",
            "geo.my": "pub struct Point { x: int32, y: int32 }\n"
                      "impl Point {\n"
                      "    fun norm2(self) -> int32 {\n"
                      "        return self.x * self.x + self.y * self.y\n"
                      "    }\n"
                      "}\n",
        })
        self.assertEqual(out, "25\n")

    def test_alias_on_import(self):
        out = run_project({
            "main.my": "from .lib import twice as dbl\n"
                       "fun main() { print(dbl(4)) }\n",
            "lib.my": "pub fun twice(n: int32) -> int32 { return n + n }\n",
        })
        self.assertEqual(out, "8\n")

    def test_local_shadows_import(self):
        # A local binding named like the import must not be rewritten.
        out = run_project({
            "main.my": "from .lib import v\n"
                       "fun main() {\n"
                       "    let v = 99\n"
                       "    print(v)\n"
                       "}\n",
            "lib.my": "pub fun v() -> int32 { return 1 }\n",
        })
        self.assertEqual(out, "99\n")

    def test_pub_from_reexport(self):
        out = run_project({
            "main.my": "from .api import helper\n"
                       "fun main() { print(helper()) }\n",
            "api.my": "pub from .provider import helper\n",
            "provider.my": "pub fun helper() -> int32 { return 5 }\n",
        })
        self.assertEqual(out, "5\n")

    def test_package_root_module(self):
        out = run_project({
            "main.my": "from .pkg import go\n"
                       "fun main() { print(go()) }\n",
            "pkg/pkg.my": "pub fun go() -> int32 { return 11 }\n",
        })
        self.assertEqual(out, "11\n")

    def test_nested_package_path(self):
        out = run_project({
            "main.my": "from .a.b.deep import answer\n"
                       "fun main() { print(answer()) }\n",
            "a/b/deep.my": "pub fun answer() -> int32 { return 42 }\n",
        })
        self.assertEqual(out, "42\n")

    def test_parent_relative_import(self):
        out = run_project({
            "app/main.my": "from ..shared import token\n"
                           "fun main() { print(token()) }\n",
            "shared.my": "pub fun token() -> int32 { return 7 }\n",
        }, entry="app/main.my")
        self.assertEqual(out, "7\n")

    def test_import_cycle_allowed(self):
        # a imports b, b imports a (types/functions); must not loop forever.
        out = run_project({
            "main.my": "from .a import start\nfun main() { print(start()) }\n",
            "a.my": "from .b import helper\n"
                    "pub fun start() -> int32 { return helper() + 1 }\n"
                    "pub fun base() -> int32 { return 10 }\n",
            "b.my": "from .a import base\n"
                    "pub fun helper() -> int32 { return base() }\n",
        })
        self.assertEqual(out, "11\n")

    def test_diamond_import_loads_once(self):
        out = run_project({
            "main.my": "from .l import a\nfrom .r import b\n"
                       "fun main() { print(a() + b()) }\n",
            "l.my": "from .base import v\npub fun a() -> int32 { return v() }\n",
            "r.my": "from .base import v\npub fun b() -> int32 { return v() }\n",
            "base.my": "pub fun v() -> int32 { return 3 }\n",
        })
        self.assertEqual(out, "6\n")

    def test_whole_module_import_member_call(self):
        out = run_project({
            "main.my": "import .lib\n"
                       "fun main() { print(lib.twice(21)) }\n",
            "lib.my": "pub fun twice(n: int32) -> int32 { return n + n }\n",
        })
        self.assertEqual(out, "42\n")

    def test_whole_module_import_with_alias(self):
        out = run_project({
            "main.my": "import .lib as L\n"
                       "fun main() { print(L.MAX) }\n",
            "lib.my": "pub const MAX: int32 = 99\n",
        })
        self.assertEqual(out, "99\n")

    def test_whole_module_dotted_path_access(self):
        out = run_project({
            "main.my": "import .a.b.deep\n"
                       "fun main() { print(a.b.deep.answer()) }\n",
            "a/b/deep.my": "pub fun answer() -> int32 { return 42 }\n",
        })
        self.assertEqual(out, "42\n")

    def test_pub_import_module_reexport(self):
        out = run_project({
            "main.my": "from .facade import lib as fac\n"
                       "fun main() { print(fac.twice(3)) }\n",
            "facade.my": "pub import .lib as lib\n",
            "lib.my": "pub fun twice(n: int32) -> int32 { return n + n }\n",
        })
        self.assertEqual(out, "6\n")

    def test_enum_ctor_via_module_member(self):
        out = run_project({
            "main.my": "import .lib as L\nfrom .lib import Color\n"
                       "fun kind(c: Color) -> int32 {\n"
                       "    return match c { Color.Red => 1, _ => 0 }\n"
                       "}\n"
                       "fun main() { print(kind(L.Color.Red)) }\n",
            "lib.my": "pub enum Color { Red, Green }\n",
        })
        self.assertEqual(out, "1\n")


class TestModuleIds(unittest.TestCase):
    """A module's id prefixes its global names. The rules are the self-hosted
    loader's (selfhost/loader.my, `module_id`), so both toolchains name things
    alike (MYLA-81): the standard library by its path under the stdlib root,
    a project module by its path under the project root, a module above the
    root with one `up` per level climbed (never colliding with one below)."""

    def test_ids(self):
        from myla.loader import _module_id
        root, std = "/w/proj/app", "/w/lib/myla"
        cases = {
            "/w/proj/app/main.my": "",
            "/w/proj/app/util/text.my": "util$text",
            "/w/lib/myla/std/io.my": "std$io",
            "/w/proj/selfhost/tokens.my": "up$selfhost$tokens",
            "/w/other/x.my": "up$up$other$x",
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(_module_id(path, "/w/proj/app/main.my", root, std), expected)


class TestLoaderErrors(unittest.TestCase):
    def _err(self, files, entry="main.my"):
        root = _project(files)
        with self.assertRaises(ModuleError) as cm:
            link(os.path.join(root, entry))
        return str(cm.exception)

    def test_private_import_rejected(self):
        msg = self._err({
            "main.my": "from .lib import secret\nfun main() {}\n",
            "lib.my": "fun secret() -> int32 { return 1 }\n",
        })
        self.assertIn("does not export 'secret'", msg)

    def test_unresolved_module(self):
        self.assertIn("cannot resolve", self._err({
            "main.my": "from .nope import x\nfun main() {}\n",
        }))

    def test_file_dir_clash(self):
        self.assertIn("ambiguous", self._err({
            "main.my": "from .dup import x\nfun main() {}\n",
            "dup.my": "pub fun x() {}\n",
            "dup/dup.my": "pub fun x() {}\n",
        }))

    def test_reserved_root_shadow(self):
        self.assertIn("reserved", self._err({
            "main.my": "from std.io import w\nfun main() {}\n",
            "std/io.my": "pub fun w() {}\n",
        }))

    def test_bare_module_used_as_value(self):
        msg = self._err({
            "main.my": "import .lib\n"
                       "fun main() { let x = lib }\n",
            "lib.my": "pub fun x() {}\n",
        })
        self.assertIn("cannot be used as a value", msg)

    def test_module_member_not_exported(self):
        msg = self._err({
            "main.my": "import .lib\nfun main() { lib.secret() }\n",
            "lib.my": "fun secret() {}\n",
        })
        self.assertIn("does not export 'secret'", msg)

    def test_import_collision(self):
        msg = self._err({
            "main.my": "from .a import f\nfrom .b import f\nfun main() {}\n",
            "a.my": "pub fun f() {}\n",
            "b.my": "pub fun f() {}\n",
        })
        self.assertIn("collides", msg)



class TestPackages(unittest.TestCase):
    """MYLA-92 (D73 (6), Architecture/Project-tool): a package `geo` with
    directory D behaves as if D were a directory `geo/` in the project root;
    imports without dots look in the project, then the packages, then the
    standard library."""

    GEO = {
        # the package root re-exports through a relative import
        "geo/src/geo.my": "pub from .shapes import Circle, area\n"
                          "pub fun origin() -> int { return 0 }\n",
        "geo/src/shapes.my": "from .units import scale\n"
                             "pub struct Circle { r: int }\n"
                             "pub fun area(c: Circle) -> int { return scale(3 * c.r * c.r) }\n",
        "geo/src/units.my": "pub fun scale(x: int) -> int { return x * 10 }\n",
        "geo/src/curves/round.my": "pub fun pi() -> int { return 3 }\n",
        "geo/src/solid/solid.my": "pub fun faces() -> int { return 6 }\n",
        # a second package that imports the first by name
        "fmt/src/fmt.my": "from geo import Circle, area\n"
                          "pub fun show(c: Circle) -> str { return f\"circle {area(c)}\" }\n",
    }
    PACKAGES = [("geo", "geo/src"), ("fmt", "fmt/src")]

    def workspace(self, app: dict[str, str], extra: dict[str, str] | None = None) -> str:
        files = dict(self.GEO)
        files.update({f"app/{rel}": src for rel, src in app.items()})
        files.update(extra or {})
        return _project(files)

    def pkgs(self, ws: str, packages=None):
        return [(n, os.path.join(ws, d)) for n, d in (self.PACKAGES if packages is None else packages)]

    def link_app(self, app, *, extra=None, packages=None, entry="main.my", **kw):
        ws = self.workspace(app, extra)
        return link(os.path.join(ws, "app", entry), packages=self.pkgs(ws, packages), **kw)

    def run_app(self, app, **kw) -> str:
        out = io.StringIO()
        Interpreter(check(self.link_app(app, **kw)), out).run()
        return out.getvalue()

    def err(self, app, **kw) -> ModuleError:
        with self.assertRaises(ModuleError) as cm:
            self.link_app(app, **kw)
        return cm.exception

    def test_root_module_and_reexports(self):
        out = self.run_app({"main.my": "import geo\nfrom geo import Circle, area\n"
                                       "fun main() {\n    print(area(Circle { r: 2 }))\n"
                                       "    print(geo.origin())\n    print(geo.area(Circle { r: 1 }))\n}\n"})
        self.assertEqual(out, "120\n0\n30\n")

    def test_submodules_and_nested_directories(self):
        out = self.run_app({"main.my": "from geo.shapes import Circle\nimport geo.curves.round as round\n"
                                       "import geo.solid\nimport geo.units\n"
                                       "fun main() {\n    print(Circle { r: 5 }.r)\n    print(round.pi())\n"
                                       "    print(geo.solid.faces())\n    print(geo.units.scale(4))\n}\n"})
        self.assertEqual(out, "5\n3\n6\n40\n")

    def test_a_package_imports_another(self):
        out = self.run_app({"main.my": "from fmt import show\nfrom geo import Circle\n"
                                       "fun main() {\n    print(show(Circle { r: 1 }))\n}\n"})
        self.assertEqual(out, "circle 30\n")

    def test_project_modules_and_relative_imports_still_resolve(self):
        out = self.run_app({"main.my": "import util\nfrom .util import two\nfun main() {\n"
                                       "    print(util.two() + two())\n}\n",
                            "util.my": "pub fun two() -> int { return 2 }\n"})
        self.assertEqual(out, "4\n")

    def test_packages_come_before_the_standard_library(self):
        ws = self.workspace({"main.my": "from geo import origin\nfrom std.io import println\n"
                                        "import other\nfun main() {\n    println(f\"{origin()} {other.x()}\")\n}\n"},
                            {"stdlib/geo.my": "pub fun origin() -> int { return 99 }\n",
                             "stdlib/other.my": "pub fun x() -> int { return 7 }\n",
                             "stdlib/std/io.my": "pub fun println(s: str) { print(s) }\n"})
        out = io.StringIO()
        prog = link(os.path.join(ws, "app", "main.my"), stdlib_root=os.path.join(ws, "stdlib"),
                    packages=self.pkgs(ws))
        Interpreter(check(prog), out).run()
        self.assertEqual(out.getvalue(), "0 7\n")

    def test_unresolved_paths_in_a_package(self):
        e = self.err({"main.my": "import geo.nope\nfun main() {}\n"})
        self.assertEqual((str(e), e.line), ("cannot resolve import 'geo.nope'", 1))
        e = self.err({"main.my": "import nope\nfun main() {}\n"})
        self.assertEqual(str(e), "cannot resolve import 'nope'")

    def test_a_package_without_its_root_module(self):
        ws = self.workspace({"main.my": "fun main() {}\nimport fmt\n"})
        d = os.path.join(ws, "geo/src/curves")
        with self.assertRaises(ModuleError) as cm:
            link(os.path.join(ws, "app", "main.my"), packages=[("fmt", d)])
        self.assertEqual((str(cm.exception), cm.exception.line),
                         (f"package 'fmt' has no root module 'fmt.my' in {d}", 2))

    def test_a_project_file_or_directory_cannot_shadow_a_package(self):
        msg = "'geo' is a dependency and cannot be shadowed by a project file or directory"
        for extra in ({"app/geo.my": "pub fun f() {}\n"}, {"app/geo/x.my": "pub fun f() {}\n"}):
            with self.subTest(extra=extra):
                e = self.err({"main.my": "fun main() {}\nfrom geo.shapes import Circle\n"}, extra=extra)
                self.assertEqual((str(e), e.line, e.column), (msg, 2, 6))
        # unless nothing imports the package by name
        out = self.run_app({"main.my": "from .geo import f\nfun main() {\n    print(f())\n}\n",
                            "geo.my": "pub fun f() -> int { return 1 }\n"})
        self.assertEqual(out, "1\n")

    def test_package_list_errors(self):
        cases = [
            ([("std", "geo/src")], "a package cannot be named 'std': it is the standard library"),
            ([("geo", "geo/src"), ("geo", "fmt/src")], "package 'geo' is given twice"),
            ([("", "geo/src")], "invalid package name ''"),
            ([("9geo", "geo/src")], "invalid package name '9geo'"),
            ([("geo-x", "geo/src")], "invalid package name 'geo-x'"),
            ([("match", "geo/src")], "invalid package name 'match'"),
        ]
        for packages, msg in cases:
            with self.subTest(packages=packages):
                self.assertEqual(str(self.err({"main.my": "fun main() {}\n"}, packages=packages)), msg)
        ws = self.workspace({"main.my": "fun main() {}\n"})
        for d, msg in (("", "package 'geo' has no directory"),
                       ("/nowhere/at/all", "package 'geo': '/nowhere/at/all' is not a directory")):
            with self.subTest(dir=d), self.assertRaises(ModuleError) as cm:
                link(os.path.join(ws, "app", "main.my"), packages=[("geo", d)])
            self.assertEqual(str(cm.exception), msg)

    def test_flags(self):
        from myla.loader import parse_package_flag
        self.assertEqual(parse_package_flag("geo=../geo/src"), ("geo", "../geo/src"))
        self.assertEqual(parse_package_flag("geo=a=b"), ("geo", "a=b"))
        self.assertEqual(parse_package_flag("=x"), ("", "x"))     # reported by link
        with self.assertRaises(ModuleError) as cm:
            parse_package_flag("geo")
        self.assertEqual(str(cm.exception), "malformed --package 'geo': expected name=dir")

    def test_module_ids_do_not_depend_on_the_package_directory(self):
        prog = self.link_app({"main.my": "from fmt import show\nimport geo.curves.round\nfun main() {}\n"},
                             extra={".myla/deps/geo-4f3c2a1/src/geo.my": self.GEO["geo/src/geo.my"],
                                    ".myla/deps/geo-4f3c2a1/src/shapes.my": self.GEO["geo/src/shapes.my"],
                                    ".myla/deps/geo-4f3c2a1/src/units.my": self.GEO["geo/src/units.my"],
                                    ".myla/deps/geo-4f3c2a1/src/curves/round.my": "pub fun pi() -> int { return 3 }\n"},
                             packages=[("geo", ".myla/deps/geo-4f3c2a1/src"), ("fmt", "fmt/src")])
        names = {getattr(d, "name", None) for d in prog.decls}
        self.assertTrue({"geo$geo$origin", "geo$shapes$Circle", "geo$units$scale",
                         "geo$curves$round$pi", "fmt$fmt$show"} <= names, names)

    def test_module_id_rules(self):
        from myla.loader import _module_id
        root, std = "/w/app/src", "/w/lib/myla"
        pkgs = [("geo", "/w/app/.myla/deps/geo-4f3c/src"), ("fmt", "/w/fmt/src")]
        cases = {
            "/w/app/.myla/deps/geo-4f3c/src/geo.my": "geo$geo",
            "/w/app/.myla/deps/geo-4f3c/src/shapes/round.my": "geo$shapes$round",
            "/w/fmt/src/fmt.my": "fmt$fmt",
            "/w/app/src/util.my": "util",
            "/w/lib/myla/std/io.my": "std$io",
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(_module_id(path, "/w/app/src/main.my", root, std, pkgs), expected)

    def test_without_packages_nothing_changes(self):
        self.assertEqual(str(self.err({"main.my": "import geo\nfun main() {}\n"}, packages=[])),
                         "cannot resolve import 'geo'")


class TestProjectRoot(unittest.TestCase):
    """The project root defaults to the entry's directory; `project_root` sets
    it, so a nested file loads like `src/main.my` does (`myla test`/`check` in
    project mode, Architecture/Project-tool)."""

    FILES = {
        "src/main.my": "fun main() {}\n",
        "src/util.my": "pub fun two() -> int { return 2 }\n",
        "src/geo/round.my": "import util\nfrom .near import one\n"
                            "fun main() {\n    print(util.two() + one())\n}\n",
        "src/geo/near.my": "pub fun one() -> int { return 1 }\n",
    }

    def test_a_nested_entry_resolves_from_the_root(self):
        root = _project(self.FILES)
        prog = link(os.path.join(root, "src/geo/round.my"), project_root=os.path.join(root, "src"))
        out = io.StringIO()
        Interpreter(check(prog), out).run()
        self.assertEqual(out.getvalue(), "3\n")
        names = {getattr(d, "name", None) for d in prog.decls}
        self.assertTrue({"main", "util$two", "geo$near$one"} <= names, names)

    def test_the_default_is_the_entry_directory(self):
        root = _project(self.FILES)
        with self.assertRaises(ModuleError) as cm:
            link(os.path.join(root, "src/geo/round.my"))
        self.assertEqual(str(cm.exception), "cannot resolve import 'util'")

    def test_shadowing_is_checked_in_the_root(self):
        root = _project(dict(self.FILES, **{"lib/geo.my": "pub fun g() {}\n"}))
        with self.assertRaises(ModuleError) as cm:
            link(os.path.join(root, "src/geo/round.my"), project_root=os.path.join(root, "src"),
                 packages=[("util", os.path.join(root, "lib"))])
        self.assertIn("'util' is a dependency", str(cm.exception))


class TestPackageFlags(unittest.TestCase):
    """`--package name=dir` (repeatable) for run, test, build and check."""

    def setUp(self):
        self.ws = _project({
            "app/main.my": "from geo import area\n#test(1)[10]\nfun f(x: int) -> int { return area(x) }\n"
                           "fun main() {\n    print(area(2))\n}\n",
            "geo/src/geo.my": "pub fun area(r: int) -> int { return r * r * 10 }\n",
        })
        self.main = os.path.join(self.ws, "app", "main.my")
        self.flag = f"geo={os.path.join(self.ws, 'geo', 'src')}"

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli_main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_run_before_and_after_the_file(self):
        self.assertEqual(self.cli("run", "--package", self.flag, self.main), (0, "40\n", ""))
        self.assertEqual(self.cli("run", self.main, "--package", self.flag), (0, "40\n", ""))

    def test_test_and_check(self):
        self.assertEqual(self.cli("test", self.main, "--package", self.flag)[:2], (0, "PASS  f #1\n\n1/1 passed.\n"))
        self.assertEqual(self.cli("check", "--package", self.flag, self.main), (0, "ok\n", ""))
        self.assertEqual(self.cli("check", self.main)[0], 1)

    def test_flag_errors(self):
        code, out, err = self.cli("check", self.main, "--package", "geo")
        self.assertEqual((code, err), (1, "module error: malformed --package 'geo': expected name=dir\n"))
        code, out, err = self.cli("check", self.main, "--package", self.flag, "--package", self.flag)
        self.assertEqual((code, err), (1, "module error: package 'geo' is given twice\n"))


class TestErrorPaths(unittest.TestCase):
    """MYLA-10: an error carries the path of the module it comes from, and the
    CLI shows that file's line."""

    MAIN = "from .bad import f\nfun main() {\n    print(f())\n}\n"

    def error_in(self, bad_src: str, main_src: str = MAIN, run: bool = False) -> MylaError:
        root = _project({"main.my": main_src, "bad.my": bad_src})
        with self.assertRaises(MylaError) as ctx:
            checker = check(link(os.path.join(root, "main.my")))
            if run:
                Interpreter(checker, io.StringIO()).run()
        self.root = root
        return ctx.exception

    def assert_in_bad(self, err: MylaError, line: int) -> None:
        self.assertEqual(err.path, os.path.realpath(os.path.join(self.root, "bad.my")))
        self.assertEqual(err.line, line)

    def test_lex_error(self):
        self.assert_in_bad(self.error_in("// one\npub fun f() -> int {\n    return $\n}\n"), 3)

    def test_parse_error(self):
        self.assert_in_bad(self.error_in("// one\npub fun f() -> int {\n    return (1\n}\n"), 4)

    def test_type_error_in_a_function(self):
        self.assert_in_bad(self.error_in(
            "// one\n// two\npub fun f() -> int {\n    return \"oops\"\n}\n"), 4)

    def test_type_error_in_a_declaration(self):
        self.assert_in_bad(self.error_in(
            "pub fun f() -> int {\n    return 1\n}\nstruct S {\n    x: Nope,\n}\n"), 5)

    def test_recursive_type(self):
        # raised after the per-declaration passes, so it needs its own file (MYLA-28)
        self.assert_in_bad(self.error_in(
            "pub fun f() -> int {\n    return 1\n}\nstruct S {\n    next: S,\n}\n"), 4)

    def test_entry_point_errors(self):
        self.assert_in_bad(self.error_in(
            "pub fun f() -> int {\n    return 1\n}\n#main\nfun g(x: int) {}\n",
            main_src="from .bad import f\n"), 5)
        self.assert_in_bad(self.error_in(
            "pub fun f() -> int {\n    return 1\n}\n#main\nfun g() {}\n#main\nfun h() {}\n",
            main_src="from .bad import f\n"), 7)

    def test_module_error(self):
        self.assert_in_bad(self.error_in(
            "// one\nfrom .missing import g\npub fun f() -> int {\n    return 1\n}\n"), 2)

    def test_runtime_error(self):
        self.assert_in_bad(self.error_in(
            "pub fun f() -> int {\n    let xs: [int] = []\n    return xs[1]\n}\n",
            run=True), 3)

    def test_runtime_error_in_a_lambda_called_elsewhere(self):
        err = self.error_in(
            "pub fun f() -> (int) -> int {\n    let xs: [int] = []\n"
            "    return (i: int) => xs[i]\n}\n",
            main_src="from .bad import f\nfun main() {\n    let g = f()\n    print(g(1))\n}\n",
            run=True)
        self.assert_in_bad(err, 3)

    def test_runtime_error_in_a_method(self):
        # a method's body is run by the method call, not `_call` (MYLA-66: the
        # native backends name the method's file, so the interpreter must too)
        err = self.error_in(
            "pub struct B { xs: [int] }\nimpl B {\n    fun get(self) -> int {\n"
            "        return self.xs[3]\n    }\n}\npub fun f() -> int {\n    return 1\n}\n",
            main_src="from .bad import B\nfun main() {\n    let b = B { xs: [] }\n"
                     "    print(b.get())\n}\n",
            run=True)
        self.assert_in_bad(err, 4)

    def test_runtime_error_in_an_operator_method(self):
        err = self.error_in(
            "pub struct P { x: int }\nimpl Add for P {\n    fun add(self, other: P) -> P {\n"
            "        return P { x: self.x / other.x }\n    }\n}\npub fun f() -> int {\n"
            "    return 1\n}\n",
            main_src="from .bad import P\nfun main() {\n    let p = P { x: 1 } + P { x: 0 }\n"
                     "    print(p.x)\n}\n",
            run=True)
        self.assert_in_bad(err, 4)

    def test_errors_in_the_entry_file_name_it(self):
        err = self.error_in("pub fun f() -> int {\n    return 1\n}\n",
                            main_src="from .bad import f\nfun main() {\n    let x: str = f()\n}\n")
        self.assertEqual(err.path, os.path.realpath(os.path.join(self.root, "main.my")))

    def test_cli_shows_the_imported_file_and_line(self):
        root = _project({"main.my": self.MAIN,
                         "bad.my": "// one\n// two\npub fun f() -> int {\n    return \"oops\"\n}\n"})
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = cli_main(["run", os.path.join(root, "main.my")])
        self.assertEqual(code, 1)
        self.assertIn("bad.my:4:", stderr.getvalue())
        self.assertIn('4 |     return "oops"', stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
