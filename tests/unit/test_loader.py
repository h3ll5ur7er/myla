"""Unit tests for the module loader / linker (v0.5.1b).

Each test writes a tiny multi-file project into a temp directory, links it, and
inspects the merged program (or runs it through the interpreter for behaviour).
"""
import io
import os
import tempfile
import unittest

from myla.errors import ModuleError
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


if __name__ == "__main__":
    unittest.main()
