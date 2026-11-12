"""Burn test: the standard library's method modules in every program without
an import (MYLA-320, D164).

`std.str`, `std.char`, `std.int`, `std.list`, `std.option` and `std.map` are
loaded with every program whose entry file isn't a module of `std`, as if it
imported them: their impls' methods on the built-in types are there, no name
of theirs is bound. A library without one of them (an old `--stdlib`
directory) goes without it. The tests run on a fixture library: a copy of
`lib/` with small stand-ins for the six modules, built in a scratch
directory, never in `lib/std/`. Every runner and tool is covered: `run`,
`test` (interpreted and `--native`), `build` for each target, `check`, the
REPL and the language server's completion.

An import path's segments may be a type's keyword (`import std.str as s`):
before MYLA-320 the parser took only identifiers there.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest

from ._native import CAN_BUILD_NATIVE, SKIP_REASON
from ._tools import STDLIB_ROOT, myla_tool, selfhost_tool
from ._lsp_scenarios import LspRequestHelpers

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))

# The stand-ins of the six modules: a method or two each, on the type the
# real module serves. `std.str` has a public function too, which a program
# reaches only through an explicit import, and its methods call primitives,
# as the standard library may (a warning, or for `__alloc` an error, in a
# program's own code); `std.list` imports `std.option`, as modules of `std`
# import what they use. `std.char`'s case is ill-typed (`is_vowel` takes no
# argument): only `myla test` of that file checks it, as a program leaves the
# implicit modules' cases out.
MODULES = {
    "str": """impl str {
    // the string and an exclamation mark
    fun shout(self) -> str {
        return self + "!"
    }

    // whether the string starts with `p`
    fun begins(self, p: str) -> bool {
        if p.len() > self.len() || __clock_ns() < 0 {
            return false
        }
        return self[:p.len()] == p
    }

    fun scratch(self) -> int {
        let a = __alloc(8)
        __free(a)
        return self.len()
    }
}

pub fun helper() -> int {
    return 7
}
""",
    "char": """impl char {
    #test('a', 1)[true]
    fun is_vowel(self) -> bool {
        return self == 'a' || self == 'e' || self == 'i' || self == 'o' || self == 'u'
    }
}
""",
    "int": """impl int {
    fun doubled(self) -> int {
        return self * 2
    }
}
""",
    "list": """from std.option import first_or

impl<T> [T] {
    fun second(self) -> T {
        return self[1]
    }

    fun head_or(self, d: T) -> T {
        if self.len() == 0 {
            return d
        }
        return first_or(Some(self[0]), d)
    }
}
""",
    "option": """impl<T> Option<T> {
    fun value_or(self, d: T) -> T {
        return match self {
            Some(v) => v,
            None => d,
        }
    }
}

pub fun first_or<T>(o: Option<T>, d: T) -> T {
    return o.value_or(d)
}
""",
    "map": """impl<K: Eq + Hash, V> [K: V] {
    fun size(self) -> int {
        return self.len()
    }
}
""",
}

# Uses one method of each module, without an import
PROGRAM = """fun main() {
    print("hi".shout())
    print("hello".begins("he"))
    print('e'.is_vowel())
    print(21.doubled())
    let xs = [1, 2, 3]
    print(xs.second())
    let none: Option<int> = None
    print(none.value_or(4))
    print(["a": 1, "b": 2].size())
    let empty: [str] = []
    print(empty.head_or("z"))
}
"""
OUTPUT = "hi!\ntrue\ntrue\n42\n2\n4\n2\nz\n"


class Fixture(unittest.TestCase):
    """A scratch directory with the fixture library (`lib/`, the six modules
    added) and the plain library's copy (`old/`, without them)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.myla = selfhost_tool("main")
        cls._tmp = tempfile.TemporaryDirectory(prefix="myla_implicit_")
        cls.work = cls._tmp.name
        cls.lib = os.path.join(cls.work, "lib")
        shutil.copytree(STDLIB_ROOT, cls.lib)
        # each stand-in is added to the real module, which other modules of
        # `std` use (std.time calls std.option's `expect`, and std.test
        # imports std.time)
        for name, text in MODULES.items():
            with open(os.path.join(cls.lib, "std", name + ".my"), "a", encoding="utf-8") as fh:
                fh.write("\n" + text)
        cls.old = os.path.join(cls.work, "old")
        shutil.copytree(STDLIB_ROOT, cls.old)
        for name in MODULES:
            gone = os.path.join(cls.old, "std", name + ".my")
            if os.path.exists(gone):
                os.remove(gone)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def line_of(self, module: str, text: str) -> int:
        """The line of the fixture library's `std.<module>` where `text` first is."""
        with open(os.path.join(self.lib, "std", module + ".my"), encoding="utf-8") as fh:
            for n, line in enumerate(fh, 1):
                if text in line:
                    return n
        raise AssertionError(f"{text!r} not in std.{module}")

    def write(self, name: str, text: str) -> str:
        path = os.path.join(self.work, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def myla_cmd(self, *argv: str, lib: str | None = None, stdin: str = "") -> subprocess.CompletedProcess:
        return subprocess.run([self.myla, *argv, "--stdlib", lib or self.lib], cwd=self.work, input=stdin,
                              capture_output=True, text=True, timeout=600)

    def build_run(self, path: str, *flags: str, runner: tuple[str, ...] = ()) -> subprocess.CompletedProcess:
        exe = path[:-3] + "-" + "-".join(f.strip("-") for f in flags or ("native",))
        built = self.myla_cmd("build", path, "-o", exe, *flags)
        self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
        return subprocess.run([*runner, exe], capture_output=True, text=True, timeout=120)


class ImplicitModules(Fixture):
    def test_run_and_check(self) -> None:
        path = self.write("prog.my", PROGRAM)
        proc = self.myla_cmd("run", path)
        self.assertEqual((proc.stdout, proc.stderr, proc.returncode), (OUTPUT, "", 0))
        proc = self.myla_cmd("check", path)
        self.assertEqual((proc.stderr, proc.returncode), ("", 0))

    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_build(self) -> None:
        path = self.write("built.my", PROGRAM)
        proc = self.build_run(path)
        self.assertEqual((proc.stdout, proc.returncode), (OUTPUT, 0), proc.stderr)

    @unittest.skipUnless(CAN_BUILD_NATIVE and shutil.which("clang") and shutil.which("ld.lld")
                         and shutil.which("qemu-aarch64"), "needs clang, ld.lld and qemu-aarch64")
    def test_build_aarch64(self) -> None:
        path = self.write("a64.my", PROGRAM)
        proc = self.build_run(path, "--target", "aarch64-linux", runner=("qemu-aarch64",))
        self.assertEqual((proc.stdout, proc.returncode), (OUTPUT, 0), proc.stderr)

    @unittest.skipUnless(CAN_BUILD_NATIVE and shutil.which("clang") and shutil.which("wasm-ld")
                         and shutil.which("node"), "needs clang, wasm-ld and node")
    def test_build_wasm(self) -> None:
        path = self.write("wasm.my", PROGRAM)
        runner = ("node", "--stack-size=7000", os.path.join(_REPO, "tools", "wasm", "run.mjs"))
        proc = self.build_run(path, "--target", "wasm32-wasi", runner=runner)
        self.assertEqual((proc.stdout, proc.returncode), (OUTPUT, 0), proc.stderr)

    def test_their_cases_are_left_out(self) -> None:
        path = self.write("no_cases.my", "fun main() {\n    print('a'.is_vowel())\n}\n")
        proc = self.myla_cmd("run", path)
        self.assertEqual((proc.stdout, proc.stderr, proc.returncode), ("true\n", "", 0))
        proc = self.myla_cmd("test", os.path.join(self.lib, "std", "char.my"))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("type error", proc.stderr)

    def test_test_cases(self) -> None:
        path = self.write("cases.my", "#test(\"a\")[\"a!\"]\nfun loud(s: str) -> str {\n    return s.shout()\n}\n\n"
                                      "#test([5, 6])[6]\nfun pick(xs: [int]) -> int {\n    return xs.second()\n}\n")
        proc = self.myla_cmd("test", path)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("2/2 passed", proc.stdout)
        if CAN_BUILD_NATIVE:
            proc = self.myla_cmd("test", path, "--native")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("2/2 passed", proc.stdout)

    def test_their_bodies_are_checked_once_called(self) -> None:
        # MYLA-359: a method or function of an implicit module that no code
        # checked calls isn't checked, one that is (even through another) is
        lib = os.path.join(self.work, "lazy_lib")
        if not os.path.exists(lib):
            shutil.copytree(self.lib, lib)
            with open(os.path.join(lib, "std", "int.my"), "a", encoding="utf-8") as fh:
                fh.write("\nimpl int {\n    fun broken(self) -> int {\n        return \"no\"\n    }\n\n"
                         "    fun calls_broken(self) -> int {\n        return self.broken()\n    }\n}\n\n"
                         "pub fun broken_fn() -> int {\n    return \"no\"\n}\n")
        path = self.write("lazy_ok.my", "fun main() {\n    print(21.doubled())\n}\n")
        proc = self.myla_cmd("run", path, lib=lib)
        self.assertEqual((proc.stdout, proc.stderr, proc.returncode), ("42\n", "", 0))
        int_my = os.path.join(lib, "std", "int.my")
        for n, body in enumerate(["print(1.broken())", "print(2.calls_broken())",
                                  "print(i.broken_fn())", "let f = i.broken_fn\n    print(f())"]):
            path = self.write(f"lazy_{n}.my", f"import std.int as i\n\nfun main() {{\n    {body}\n}}\n")
            proc = self.myla_cmd("check", path, lib=lib)
            self.assertEqual(proc.returncode, 1, body)
            self.assertIn("type error: return type mismatch", proc.stderr, body)
            self.assertIn("--> " + int_my + ":", proc.stderr, body)

    def test_their_bodies_are_parsed_once_called(self) -> None:
        # MYLA-359: an implicit module's function bodies are lexed and
        # parsed once the checker needs one, a lex or parse error in one at
        # its place in the module; a type error in one read late at its
        # place too; the module's own `myla test` reads them all
        lib = os.path.join(self.work, "unparsed_lib")
        if not os.path.exists(lib):
            shutil.copytree(self.lib, lib)
            with open(os.path.join(lib, "std", "int.my"), "a", encoding="utf-8") as fh:
                fh.write("\nimpl int {\n    fun garbled(self) -> int {\n        let = self\n        return 1\n    }\n\n"
                         "    fun odd_char(self) -> int {\n        return self @ 2\n    }\n\n"
                         "    fun mistyped(self) -> int {\n        let s = \"}\" // }\n        return s\n    }\n}\n\n"
                         "pub fun garbled_fn() -> int {\n    return (1 +) * 2\n}\n")
        int_my = os.path.join(lib, "std", "int.my")
        with open(int_my, encoding="utf-8") as fh:
            lines = fh.read().split("\n")

        def at(line_text: str, text: str) -> str:
            # the place of `text` on the last line holding `line_text`
            n = max(i for i, line in enumerate(lines, 1) if line_text in line)
            return f"{int_my}:{n}:{lines[n - 1].index(text) + 1}"

        path = self.write("unparsed_ok.my", "fun main() {\n    print(21.doubled())\n}\n")
        for cmd in ("run", "check"):
            proc = self.myla_cmd(cmd, path, lib=lib)
            self.assertEqual((proc.stderr, proc.returncode), ("", 0), cmd)
        for body, error, where in [
            ("print(1.garbled())", "parse error: expected variable name, found '='", at("let = self", "= self")),
            ("print(1.odd_char())", "lex error: unexpected character '@'", at("self @ 2", "@ 2")),
            ("print(i.garbled_fn())", "parse error: expected an expression, found ')'", at("(1 +) * 2", ") * 2")),
            ("print(1.mistyped())", "type error: return type mismatch", at("return s", "return s")),
        ]:
            path = self.write("unparsed.my", f"import std.int as i\n\nfun main() {{\n    {body}\n}}\n")
            proc = self.myla_cmd("check", path, lib=lib)
            self.assertEqual(proc.returncode, 1, body)
            self.assertIn(error, proc.stderr, body)
            self.assertIn("--> " + where + "\n", proc.stderr, body)
        proc = self.myla_cmd("test", int_my, lib=lib)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("lex error: unexpected character '@'\n  --> " + at("self @ 2", "@ 2") + "\n", proc.stderr)

    def lib_with(self, name: str, module: str, text: str) -> str:
        """A copy of the fixture library, `text` appended to `std.<module>`."""
        lib = os.path.join(self.work, name)
        if not os.path.exists(lib):
            shutil.copytree(self.lib, lib)
            with open(os.path.join(lib, "std", module + ".my"), "a", encoding="utf-8") as fh:
                fh.write("\n" + text)
        return lib

    def test_a_body_without_its_brace_keeps_the_methods_after_it(self) -> None:
        # MYLA-416 (Z1): the skip of a body that misses a `}` would run to the
        # impl's `}` and take the methods after it for body text; a line that
        # starts with a declaration's keyword inside a skipped body sends it
        # back to the lexer, so the error is the eager one, at the method
        # after the broken one, also where one more `}` closes the impl
        broken = ("impl int {\n    fun q4_ok(self) -> int { return self + 1 }\n\n"
                  "    fun q4_missing(self) -> int {\n        if self > 0 { return 1\n        return 2\n    }\n\n"
                  "    fun q4_after(self) -> int { return 3 }\n}\n")
        error = "parse error: expected an expression, found 'fun'"
        for name, text in [("brace_a", broken), ("brace_b", broken + "}\n")]:
            lib = self.lib_with(name, "int", text)
            int_my = os.path.join(lib, "std", "int.my")
            with open(int_my, encoding="utf-8") as fh:
                n = max(i for i, line in enumerate(fh.read().split("\n"), 1) if "fun q4_after" in line)
            where = f"--> {int_my}:{n}:5\n"
            eager = self.myla_cmd("check", int_my, lib=lib)
            self.assertIn(error, eager.stderr, name)
            self.assertIn(where, eager.stderr, name)
            for call in ("q4_ok", "q4_after"):
                path = self.write(f"{name}_{call}.my", f"fun main() {{\n    print(1.{call}())\n}}\n")
                for cmd in ("check", "run"):
                    proc = self.myla_cmd(cmd, path, lib=lib)
                    self.assertEqual(proc.returncode, 1, (name, call, cmd, proc.stdout))
                    self.assertIn(error + "\n  " + where, proc.stderr, (name, call, cmd))

    def test_a_declaration_after_a_missing_brace_anywhere_on_its_line(self) -> None:
        # MYLA-545 (Z1's residual): a declaration's keyword that doesn't start
        # its line, after a comment, a `};`, a `#test` or another attribute,
        # sends the skipped body back to the lexer too: the error is the eager
        # one at load, not a method that is silently gone (on the eager one's
        # line: the entry's own `#test` is parsed, an imported module's isn't)
        head = ("impl int {\n    fun q5_ok(self) -> int { return self + 1 }\n\n"
                "    fun q5_missing(self) -> int {\n        if self > 0 { return 1\n        return 2\n    }")
        for name, text in [("swallow_comment", head + "\n\n    /* the next one */ fun q5_after(self) -> int { return 3 }\n}\n}\n"),
                           ("swallow_semi", head + "; fun q5_after(self) -> int { return 3 }\n}\n}\n"),
                           ("swallow_test", head + "\n\n    #test(1)[3] fun q5_after(self) -> int { return 3 }\n}\n}\n"),
                           ("swallow_derive", "pub fun q5_a(x: int) -> int {\n    if x > 0 { return 1\n    return 2\n}\n"
                                              "#derive(Eq) pub struct Q5 { x: int }\n}\n")]:
            lib = self.lib_with(name, "int", text)
            int_my = os.path.join(lib, "std", "int.my")
            eager = self.myla_cmd("check", int_my, lib=lib)
            self.assertEqual(eager.returncode, 1, name)
            self.assertTrue(eager.stderr.startswith("parse error: "), (name, eager.stderr))
            first = eager.stderr.split("\n")[:4]
            path = self.write(f"{name}.my", "fun main() {\n    print(1.q5_ok())\n}\n")
            for cmd in ("check", "run"):
                proc = self.myla_cmd(cmd, path, lib=lib)
                self.assertEqual(proc.returncode, 1, (name, cmd, proc.stdout))
                lines = proc.stderr.split("\n")[:4]
                self.assertTrue(lines[0].startswith("parse error: expected an expression, found "), (name, cmd, lines))
                self.assertEqual(lines[1].rsplit(":", 1)[0], first[1].rsplit(":", 1)[0], (name, cmd))
                self.assertEqual(lines[3], first[3], (name, cmd))

    def test_a_signature_over_two_lines_keeps_its_body(self) -> None:
        # MYLA-416 (Z2): a body is keyed by the place of its `{`, which the
        # lexer keeps below the limits of the key, not its `fun`'s, which may
        # be past them on the line before: two methods' keys collided and
        # both ran the second one's body
        line1 = "impl int { " + " " * (5000 - 1 - len("impl int { ")) + "fun q_a(self,"
        line2 = ") -> int { return 1 };"
        line2 += " " * (904 - 1 - len(line2)) + "fun q_b(self) -> int { return 2 }"
        self.assertEqual((line1.index("fun") + 1, line2.index("fun") + 1), (5000, 904))
        lib = self.lib_with("key_lib", "int", line1 + "\n" + line2 + "\n}\n")
        path = self.write("keys.my", "fun main() {\n    print(7.q_a())\n    print(7.q_b())\n}\n")
        proc = self.myla_cmd("run", path, lib=lib)
        self.assertEqual((proc.stdout, proc.stderr, proc.returncode), ("1\n2\n", "", 0))
        if CAN_BUILD_NATIVE:
            exe = os.path.join(self.work, "keys_bin")
            built = self.myla_cmd("build", path, "-o", exe, lib=lib)
            self.assertEqual(built.returncode, 0, built.stderr)
            proc = subprocess.run([exe], capture_output=True, text=True, timeout=60)
            self.assertEqual(proc.stdout, "1\n2\n")

    def test_a_test_attribute_is_skipped_only_where_one_may_stand(self) -> None:
        # MYLA-416 (Z4): a module's `#test` cases are skipped unlexed only
        # where an attribute may stand, at the start of a line: one in the
        # middle of a statement is lexed, its error the eager one, imported
        # as when checked itself. A body read late is lexed as the module
        # read whole, its cases at the start of a line left out as there
        self.write("attr/m.my", "pub fun f() -> int {\n    let x = 1 #test(\"anything\", @ $)[1 2 3]\n    return x\n}\n")
        main = self.write("attr/main.my", "from .m import f\n\nfun main() {\n    print(f())\n}\n")
        m_my = os.path.join(self.work, "attr", "m.my")
        for target in (main, m_my):
            proc = self.myla_cmd("check", target)
            self.assertEqual(proc.returncode, 1, target)
            self.assertIn("lex error: unexpected character '@'\n  --> " + m_my + ":2:33\n", proc.stderr, target)
        lib = self.lib_with("case_lib", "int", "impl int {\n    fun with_case(self) -> int {\n        #test(1)[2]\n        return 5\n    }\n}\n")
        path = self.write("with_case.my", "fun main() {\n    print(1.with_case())\n}\n")
        proc = self.myla_cmd("run", path, lib=lib)
        self.assertEqual((proc.stdout, proc.stderr, proc.returncode), ("5\n", "", 0))

    def test_the_repl(self) -> None:
        proc = self.myla_cmd("repl", stdin="\"ab\".shout()\n3.doubled()\n")
        self.assertEqual(proc.stdout, "\"ab!\"\n6\n", proc.stderr)

    def test_a_module_of_the_program_sees_them(self) -> None:
        self.write("pkg/helpers.my", "pub fun twice_loud(s: str) -> str {\n    return s.shout().shout()\n}\n")
        path = self.write("pkg/main.my", "from .helpers import twice_loud\n\nfun main() {\n    print(twice_loud(\"x\"))\n}\n")
        proc = self.myla_cmd("run", path)
        self.assertEqual((proc.stdout, proc.stderr, proc.returncode), ("x!!\n", "", 0))

    def test_an_explicit_import_still_works(self) -> None:
        path = self.write("explicit.my", "import std.str as s\nfrom std.str import helper\nimport std.list as l\n\n"
                                         "fun main() {\n    print(s.helper() + helper())\n    print(\"a\".shout())\n}\n")
        proc = self.myla_cmd("run", path)
        self.assertEqual((proc.stdout, proc.stderr, proc.returncode), ("14\na!\n", "", 0))

    def test_no_name_is_bound(self) -> None:
        # a public function of an implicit module is reached only through an
        # import, and the program may declare the name itself
        path = self.write("unbound.my", "fun main() {\n    print(helper())\n}\n")
        proc = self.myla_cmd("check", path)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("unknown function 'helper'", proc.stderr)
        path = self.write("own.my", "fun helper() -> int {\n    return 1\n}\n\nfun first_or() -> int {\n    return 2\n}\n\n"
                                    "fun main() {\n    print(helper() + first_or())\n}\n")
        proc = self.myla_cmd("run", path)
        self.assertEqual((proc.stdout, proc.stderr, proc.returncode), ("3\n", "", 0))

    def test_a_program_s_own_method_of_the_name_is_a_duplicate(self) -> None:
        path = self.write("dup.my", "impl str {\n    fun shout(self) -> str {\n        return self\n    }\n}\n\n"
                                    "fun main() {\n    print(\"a\".shout())\n}\n")
        proc = self.myla_cmd("check", path)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("type error: duplicate method 'shout' for type 'str'\n  --> " + path + ":2:5", proc.stderr)
        self.assertIn("note: 'shout' for 'str' is first defined in std.str, which every program sees, at "
                      + os.path.join(self.lib, "std", "str.my") + f":{self.line_of('str', 'fun shout')}:5", proc.stderr)
        # the same with the module imported
        path = self.write("dup2.my", "import std.str as s\n\nimpl str {\n    fun shout(self) -> str {\n        return self\n    }\n}\n")
        proc = self.myla_cmd("check", path)
        self.assertIn("  --> " + path + ":4:5", proc.stderr)
        self.assertIn("first defined in std.str", proc.stderr)

    def test_a_library_without_them(self) -> None:
        # an old --stdlib directory: nothing is loaded, nothing is missing
        path = self.write("plain.my", "fun main() {\n    print(1)\n}\n")
        proc = self.myla_cmd("run", path, lib=self.old)
        self.assertEqual((proc.stdout, proc.stderr, proc.returncode), ("1\n", "", 0))
        path = self.write("needs.my", "fun main() {\n    print(\"a\".shout())\n}\n")
        proc = self.myla_cmd("check", path, lib=self.old)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("'shout'", proc.stderr)

    def test_a_module_of_std_imports_what_it_uses(self) -> None:
        # checked on its own, a std module sees only its imports' methods
        uses = os.path.join(self.lib, "std", "uses_shout.my")
        with open(uses, "w", encoding="utf-8") as fh:
            fh.write("pub fun loud(s: str) -> str {\n    return s.shout()\n}\n")
        self.addCleanup(os.remove, uses)
        proc = self.myla_cmd("check", uses)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("'shout'", proc.stderr)
        with open(uses, "w", encoding="utf-8") as fh:
            fh.write("import std.str as s\n\npub fun loud(t: str) -> str {\n    return t.shout()\n}\n")
        proc = self.myla_cmd("check", uses)
        self.assertEqual((proc.stderr, proc.returncode), ("", 0))
        # and its #test cases run without the others
        proc = self.myla_cmd("test", os.path.join(self.lib, "std", "list.my"))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


class TypeKeywordSegments(Fixture):
    """`str`, `bool` and the sized integers are keywords, and may name a
    module in an import path (MYLA-320)."""

    def test_type_keywords_in_import_paths(self) -> None:
        for name in ("bool", "int8", "uint64"):
            self.write(f"kw/{name}.my", f"pub fun tag() -> str {{\n    return \"{name}\"\n}}\n")
        path = self.write("kw/main.my", "import .bool as b\nfrom .int8 import tag\nimport .uint64 as u\n\n"
                                        "fun main() {\n    print(b.tag() + tag() + u.tag())\n}\n")
        proc = self.myla_cmd("run", path, lib=self.old)
        self.assertEqual((proc.stdout, proc.stderr, proc.returncode), ("boolint8uint64\n", "", 0))

    def test_an_alias_is_still_a_name(self) -> None:
        path = self.write("kw_alias.my", "import std.str as str\n")
        proc = self.myla_cmd("check", path)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("parse error: expected an alias name after 'as', found 'str'", proc.stderr)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class ImplicitCompletion(LspRequestHelpers, unittest.TestCase):
    """The language server completes the implicit modules' methods."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.binary = myla_tool("tools/lsp/main.my", "lsp")
        cls._tmp = tempfile.TemporaryDirectory(prefix="myla_implicit_lsp_")
        cls.lib = os.path.join(cls._tmp.name, "lib")
        shutil.copytree(STDLIB_ROOT, cls.lib)
        for name, text in MODULES.items():
            with open(os.path.join(cls.lib, "std", name + ".my"), "w", encoding="utf-8") as fh:
                fh.write(text)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def server_command(self) -> list[str]:
        return [self.binary, "--stdlib", self.lib]

    def labels(self, uri, line, character):
        return sorted(i["label"] for i in self.at("textDocument/completion", uri, line, character)["items"])

    def test_methods_of_the_implicit_modules(self) -> None:
        head = ("fun main() {\n    let s = \"hi\"\n    let c = 'a'\n    let n: int = 2\n    let xs = [1, 2]\n"
                "    let m = [\"a\": 1]\n")
        # (std.hash is implicit too: its `Hash` impls give `hash`, MYLA-313)
        for typed, expected in (("s.", ["begins", "hash", "scratch", "shout"]), ("c.", ["hash", "is_vowel"]),
                                ("n.", ["doubled", "hash"]),
                                ("xs.", ["hash", "head_or", "second"]), ("m.", ["size"])):
            with self.subTest(typed=typed):
                uri = self.open(head + "    " + typed + "\n}\n", name=typed[:-1] + ".my")
                self.assertEqual(self.labels(uri, 6, 4 + len(typed)), expected)


if __name__ == "__main__":
    unittest.main()
