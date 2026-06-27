"""Unit tests for assembly generation (no assembler/linker required)."""
import unittest

from myla.compiler import compile_to_asm
from myla.lexer import tokenize
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


if __name__ == "__main__":
    unittest.main()
