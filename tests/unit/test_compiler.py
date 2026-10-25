"""Unit tests for assembly generation (no assembler/linker required)."""
import os
import re
import tempfile
import unittest
from unittest import mock

from myla.compiler import compile_to_asm
from myla import ast
from myla.compiler.codegen_x86 import CodeGen, _may_write, _place_root
from myla.lexer import tokenize
from myla.loader import default_stdlib_root, link
from myla.parser import parse
from myla.types import check


def asm_for(src: str) -> str:
    return compile_to_asm(check(parse(tokenize(src))))


class TestAsmGeneration(unittest.TestCase):
    def test_emits_entry_and_runtime(self):
        asm = asm_for("#main\nfun run() {\n    print(1)\n}\n")
        self.assertIn(".global _start", asm)
        self.assertIn("call myla_run", asm)      # entry by attribute name
        self.assertIn("__print_int:", asm)        # runtime helper present
        self.assertIn("syscall", asm)

    def test_string_literal_in_rodata(self):
        asm = asm_for('fun main() {\n    print("hi")\n}\n')
        self.assertIn(".section .rodata", asm)
        self.assertIn(".quad 2", asm)             # length prefix of "hi"

    def test_deterministic(self):
        src = "fun main() {\n    let x = 1 + 2\n    print(x)\n}\n"
        self.assertEqual(asm_for(src), asm_for(src))

    def test_function_labels_mangled(self):
        asm = asm_for(
            "fun add(a: int, b: int) -> int {\n    return a + b\n}\n"
            "fun main() {\n    print(add(1, 2))\n}\n"
        )
        self.assertIn("myla_add:", asm)
        self.assertIn("myla_main:", asm)


def diamond_struct_chain(depth: int) -> str:
    """Structs S0..S<depth> where each holds two fields of the next one, and the
    last holds a list: 2**depth paths lead from S0 to the list, but only
    depth+1 distinct types exist."""
    decls = [f"struct S{i} {{ a: S{i + 1}, b: S{i + 1} }}\n" for i in range(depth)]
    decls.append(f"struct S{depth} {{ xs: [int] }}\n")
    return ("".join(decls)
            + "fun first(s: S0) -> int {\n    return 1\n}\n"
            + "fun main() {\n    print(2)\n}\n")


class TestListTypeCollection(unittest.TestCase):
    """The code generator collects every list/map type to emit their helpers
    (MYLA-60). It must visit each type once, not once per path through the
    type graph, or big programs (the self-hosted compiler) take minutes."""

    def test_visits_each_type_once(self):
        calls = 0
        original = CodeGen._gather_list_types

        def counting(self, *args, **kwargs):
            nonlocal calls
            calls += 1
            return original(self, *args, **kwargs)

        with mock.patch.object(CodeGen, "_gather_list_types", counting):
            asm = asm_for(diamond_struct_chain(16))
        self.assertIn("__drop_list_int32:", asm)   # the list type was still found
        self.assertLess(calls, 1000)                # 2**16 paths if not memoized

    def test_helpers_are_emitted_in_a_stable_order(self):
        src = diamond_struct_chain(3) + (
            "struct M { m: [str: [uint8]], t: ([bool], StringBuilder) }\n"
            "fun g(m: M) -> int {\n    return 0\n}\n")
        asm = asm_for(src)
        labels = [line for line in asm.splitlines()
                  if line.startswith(("__drop_list_", "__drop_map_", "__sb_new"))]
        # Recorded from the unmemoized implementation: memoization must not
        # change which helpers are emitted or their order.
        self.assertEqual(labels, [
            "__sb_new:", "__drop_list_int32:", "__drop_map_str_L_uint8:",
            "__drop_list_uint8:", "__drop_list_bool:",
        ])
        self.assertEqual(asm, asm_for(src))


MAIN_SRC = (
    "from .lib import twice\n"          # line 1
    "\n"
    "fun main() {\n"                    # line 3
    "    let x = twice(4)\n"            # line 4, column 5
    "    print(x)\n"                    # line 5
    "    let f = (n: int) => n + 1\n"   # line 6
    "    print(f(x))\n"                 # line 7
    "}\n"
)
LIB_SRC = (
    "pub fun twice(n: int) -> int {\n"  # line 1
    "    return n * 2\n"                # line 2, column 5
    "}\n"
)


class TestLineTables(unittest.TestCase):
    """`.file`/`.loc` directives let the assembler build a DWARF line table, so
    gdb can break on and step through Myla source lines (MYLA-71)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.main = os.path.join(os.path.realpath(tmp.name), "main.my")
        self.lib = os.path.join(os.path.realpath(tmp.name), "lib.my")
        for path, src in ((self.main, MAIN_SRC), (self.lib, LIB_SRC)):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(src)

    def asm(self, debug: bool) -> str:
        checker = check(link(self.main, stdlib_root=default_stdlib_root()))
        return compile_to_asm(checker, debug=debug)

    def file_numbers(self, asm: str) -> dict[str, int]:
        return {path: int(num) for num, path in
                re.findall(r'^\t\.file (\d+) "(.*)"$', asm, re.M)}

    def function(self, asm: str, label: str) -> list[str]:
        """The lines of one generated function, from its label to its `ret`."""
        lines = asm.splitlines()
        start = lines.index(label)
        return lines[start:lines.index("\tret", start) + 2]

    def test_no_line_info_by_default(self):
        asm = self.asm(debug=False)
        self.assertNotIn(".file", asm)
        self.assertNotIn(".loc", asm)

    def test_every_module_gets_a_file_entry(self):
        files = self.file_numbers(self.asm(debug=True))
        self.assertEqual(set(files), {self.main, self.lib})
        self.assertEqual(sorted(files.values()), [1, 2])

    def test_functions_and_statements_carry_their_source_lines(self):
        asm = self.asm(debug=True)
        files = self.file_numbers(asm)
        main, lib = files[self.main], files[self.lib]
        body = self.function(asm, "myla_main:")
        self.assertEqual(body[1], f"\t.loc {main} 3 1")      # `fun main` itself
        self.assertIn(f"\t.loc {main} 4 5", body)             # let x = twice(4)
        self.assertTrue(any(l.startswith(f"\t.loc {main} 5 ") for l in body))
        body = self.function(asm, "myla_lib$twice:")
        self.assertEqual(body[1], f"\t.loc {lib} 1 5")       # imported module
        self.assertIn(f"\t.loc {lib} 2 5", body)              # return n * 2

    def test_lambda_bodies_point_into_their_module(self):
        asm = self.asm(debug=True)
        body = self.function(asm, "myla___lambda_0:")
        locs = [l for l in body if ".loc" in l]
        self.assertEqual(locs[0], f"\t.loc {self.file_numbers(asm)[self.main]} 6 13")
        self.assertEqual(len(locs), len(set(locs)), "repeated .loc for one position")

    def test_code_after_a_function_has_no_source_line(self):
        # line 0 means "no source": runtime helpers emitted after the last
        # function must not be attributed to its last statement
        asm = self.asm(debug=True)
        for label in ("myla_main:", "myla_lib$twice:", "myla___lambda_0:"):
            self.assertRegex(self.function(asm, label)[-1], r"^\t\.loc \d+ 0 0$")



class TestMatchScrutineeOwnership(unittest.TestCase):
    """MYLA-2: the native match copy holds references only when an arm may
    write to the variable the scrutinee comes from."""

    def arms_write(self, arm: str, scrutinee: str = "s.items") -> bool:
        src = (
            "struct S { items: [int], n: int }\n"
            "impl S {\n    fun bump(var self) { self.n = self.n + 1 }\n}\n"
            "fun main() {\n"
            "    var s = S { items: [1], n: 0 }\n"
            "    var other = [1]\n"
            f"    match {scrutinee} {{\n        xs => {{\n            {arm}\n        }}\n    }}\n"
            "}\n"
        )
        main = next(d for d in parse(tokenize(src)).decls
                    if isinstance(d, ast.FunDecl) and d.name == "main")
        match = main.body.statements[-1].expr
        root = _place_root(match.scrutinee)
        return any(_may_write([arm.guard, arm.body], root) for arm in match.arms)

    def test_place_roots(self):
        def root(code):
            return _place_root(parse(tokenize(f"fun f() {{\n    let v = {code}\n}}\n"))
                               .decls[0].body.statements[0].init)
        self.assertEqual(root("a"), "a")
        self.assertEqual(root("a.b[3].c"), "a")
        self.assertIsNone(root("g(a)"))
        self.assertIsNone(root("[1, 2]"))

    def test_reads_are_not_writes(self):
        self.assertFalse(self.arms_write("print(len(xs) + s.n)"))
        self.assertFalse(self.arms_write("push(other, s.n)"))
        self.assertFalse(self.arms_write("other = s.items"))

    def test_writes_through_the_root_variable(self):
        self.assertTrue(self.arms_write("s.n = 2"))
        self.assertTrue(self.arms_write("s.items[0] = 2"))
        self.assertTrue(self.arms_write("push(s.items, 2)"))
        self.assertTrue(self.arms_write("s.items |> push(2)"))  # parsed as push(s.items, 2)
        self.assertTrue(self.arms_write("s.bump()"))           # may take `var self`
        self.assertTrue(self.arms_write("if true {\n                s = S { items: [], n: 1 }\n            }"))
        self.assertTrue(self.arms_write("push(s.items, 1)", scrutinee="s"))



class TestSelfHostedFloatRuntime(unittest.TestCase):
    def test_generated_runtime_matches_the_python_backend(self):
        # selfhost/codegen.my embeds the Python backend's float runtime and
        # __char_to_str (scripts/gen_selfhost_runtime.py); after changing
        # those, rerun the script (MYLA-29).
        import importlib.util
        root = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
        spec = importlib.util.spec_from_file_location(
            "gen_runtime", os.path.join(root, "scripts", "gen_selfhost_runtime.py"))
        gen = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gen)
        with open(os.path.join(root, "selfhost", "codegen.my"), encoding="utf-8") as fh:
            src = fh.read()
        region = src[src.index(gen.BEGIN):src.index(gen.END) + len(gen.END)]
        self.assertEqual(region, gen.render(),
                         "run scripts/gen_selfhost_runtime.py")


if __name__ == "__main__":
    unittest.main()
