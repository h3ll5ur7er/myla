"""Unit tests for the language server's pure features (no pygls needed):
positions, document symbols, definition, references and completion (MYLA-52).
All positions are 0-based UTF-16, as in LSP."""
import unittest

from myla.lsp.completion import completions
from myla.lsp.definition import definition_at
from myla.lsp.diagnostics import Location, SourceRange
from myla.lsp.positions import from_lsp_character, identifier_end_column, to_lsp_position
from myla.lsp.references import references_at
from myla.lsp.symbols import SymbolKind, document_symbols

PATH = "/tmp/doc.my"


def rng(line: int, start: int, end: int) -> SourceRange:
    return SourceRange(line, start, line, end)


class TestPositions(unittest.TestCase):
    def test_columns_count_utf16_code_units(self):
        lines = ['let s = "😀é" + x']
        self.assertEqual(to_lsp_position(lines, 1, 1), (0, 0))
        self.assertEqual(to_lsp_position(lines, 1, 10), (0, 9))     # the 😀
        self.assertEqual(to_lsp_position(lines, 1, 11), (0, 11))    # 😀 is two units
        self.assertEqual(to_lsp_position(lines, 1, 12), (0, 12))    # é is one

    def test_positions_are_clamped_to_the_document(self):
        lines = ["ab", "cd"]
        self.assertEqual(to_lsp_position(lines, 0, 0), (0, 0))
        self.assertEqual(to_lsp_position(lines, 9, 1), (1, 0))
        self.assertEqual(to_lsp_position(lines, 1, 99), (0, 2))     # one past the end
        self.assertEqual(to_lsp_position([], 3, 3), (0, 0))

    def test_crlf_lines(self):
        lines = "fun a() {}\r\nfun b() {}\r\n".splitlines()
        self.assertEqual(lines, ["fun a() {}", "fun b() {}"])
        self.assertEqual(to_lsp_position(lines, 2, 5), (1, 4))

    def test_from_lsp_character(self):
        text = 'f("😀").x'
        self.assertEqual(from_lsp_character(text, 0), 0)
        self.assertEqual(from_lsp_character(text, 3), 3)            # before 😀
        self.assertEqual(from_lsp_character(text, 5), 4)            # after it
        self.assertEqual(from_lsp_character(text, 4), 3)            # inside the pair
        self.assertEqual(from_lsp_character(text, 99), len(text))

    def test_identifier_end_column(self):
        self.assertEqual(identifier_end_column("let abc = 1", 5), 8)
        self.assertEqual(identifier_end_column("x + 1", 3), 4)       # not an identifier
        self.assertEqual(identifier_end_column("ab", 9), 10)         # past the end


class TestSymbolRanges(unittest.TestCase):
    """MYLA-48: the selection range is the declaration's name token."""

    def symbols(self, source: str):
        return {s.name: s for s in _flat(document_symbols(PATH, source))}

    def test_short_names_inside_the_keyword(self):
        syms = self.symbols("fun un() {}\nconst t: int = 1\nstruct S { s: int }\nenum E { E }\n")
        self.assertEqual(syms["un"].selection_range, rng(0, 4, 6))
        self.assertEqual(syms["t"].selection_range, rng(1, 6, 7))
        self.assertEqual(syms["S"].selection_range, rng(2, 7, 8))
        self.assertEqual(syms["s"].selection_range, rng(2, 11, 12))

    def test_variant_named_like_its_enum(self):
        [enum] = document_symbols(PATH, "enum E { E, F }\n")
        self.assertEqual(enum.selection_range, rng(0, 5, 6))
        self.assertEqual([(v.name, v.selection_range) for v in enum.children],
                         [("E", rng(0, 9, 10)), ("F", rng(0, 12, 13))])

    def test_generic_declarations(self):
        syms = self.symbols("fun id<T>(x: T) -> T {\n    return x\n}\n"
                            "struct Box<T> { v: T }\n"
                            "trait Tr<T> {\n    fun get(self) -> T\n}\n"
                            "impl<T> Box<T> {\n    fun un(self) -> T {\n        return self.v\n    }\n}\n"
                            "typealias ty = int\n")
        self.assertEqual(syms["id"].selection_range, rng(0, 4, 6))
        self.assertEqual(syms["Box"].selection_range, rng(3, 7, 10))
        self.assertEqual(syms["Tr"].selection_range, rng(4, 6, 8))
        self.assertEqual(syms["get"].selection_range, rng(5, 8, 11))
        self.assertEqual(syms["Box<T>"].selection_range, rng(7, 8, 11))  # the impl
        self.assertEqual(syms["un"].selection_range, rng(8, 8, 10))
        self.assertEqual(syms["ty"].selection_range, rng(12, 10, 12))

    def test_impl_selects_its_target(self):
        source = ("trait G<T> {\n    fun g(self) -> T\n}\n"
                  "impl G<int32> for int32 {\n    fun g(self) -> int32 {\n        return self\n    }\n}\n")
        impl = document_symbols(PATH, source)[1]
        self.assertEqual((impl.name, impl.selection_range), ("int32", rng(3, 18, 23)))

    def test_attributes_and_pub_before_the_keyword(self):
        syms = self.symbols("#test(2)[4]\npub fun f(f: int) -> int {\n    return f * 2\n}\n")
        self.assertEqual(syms["f"].selection_range, rng(1, 8, 9))

    def test_names_after_astral_characters(self):
        syms = self.symbols('const A: str = "😀"; const B: int = 1\n'.replace("; ", "\n"))
        self.assertEqual(syms["B"].selection_range, rng(1, 6, 7))
        syms = self.symbols('struct P { a: str }\nfun f() -> P {\n    return P { a: "😀" }\n}\n')
        self.assertEqual(syms["f"].selection_range, rng(1, 4, 5))

    def test_declarations_separated_by_semicolons(self):
        syms = self.symbols("const A: int = 1; const B: int = A\nfun f() {}; fun g() {}\n")
        self.assertEqual(syms["A"].selection_range, rng(0, 6, 7))
        self.assertEqual(syms["B"].selection_range, rng(0, 24, 25))
        self.assertEqual(syms["g"].selection_range, rng(1, 16, 17))

    def test_outline(self):
        source = ("struct P { x: int, y: int }\nenum Sh { Dot, Box(int) }\n"
                  "trait Area {\n    fun area(self) -> int\n}\n"
                  "impl Area for P {\n    fun area(self) -> int {\n        return self.x\n    }\n}\n"
                  "fun main() {}\n")
        outline = [(s.name, s.kind, [c.name for c in s.children])
                   for s in document_symbols(PATH, source)]
        self.assertEqual(outline, [
            ("P", SymbolKind.STRUCT, ["x", "y"]),
            ("Sh", SymbolKind.ENUM, ["Dot", "Box"]),
            ("Area", SymbolKind.INTERFACE, ["area"]),
            ("P", SymbolKind.IMPL, ["area"]),
            ("main", SymbolKind.FUNCTION, []),
        ])

    def test_parse_error_gives_no_symbols(self):
        self.assertEqual(document_symbols(PATH, "fun (\n"), [])


SOURCE = ("fun un(n: int) -> int {\n"
          "    return n\n"
          "}\n"
          "fun main() {\n"
          "    // un in a comment\n"
          "    print(un(1) + un(2))\n"
          "    print(\"un\")\n"
          "}\n")


class TestDefinitionAndReferences(unittest.TestCase):
    def test_definition_jumps_to_the_name(self):
        self.assertEqual(definition_at(PATH, SOURCE, 5, 11), Location(PATH, rng(0, 4, 6)))

    def test_definition_falls_back_to_the_workspace(self):
        elsewhere = Location("/tmp/other.my", rng(3, 4, 9))
        source = "fun main() {\n    other()\n}\n"
        self.assertEqual(definition_at(PATH, source, 1, 5, resolver=lambda n: [elsewhere]), elsewhere)
        self.assertIsNone(definition_at(PATH, source, 1, 5))
        self.assertIsNone(definition_at(PATH, source, 1, 0))         # not on an identifier

    def test_references_skip_comments_and_strings(self):
        refs = [loc.range for loc in references_at(PATH, SOURCE, 5, 11)]
        self.assertEqual(refs, [rng(0, 4, 6), rng(5, 10, 12), rng(5, 18, 20)])

    def test_references_without_the_declaration(self):
        refs = [loc.range for loc in references_at(PATH, SOURCE, 5, 11, include_declaration=False)]
        self.assertEqual(refs, [rng(5, 10, 12), rng(5, 18, 20)])

    def test_references_merge_the_workspace_without_duplicates(self):
        extra = [Location(PATH, rng(0, 4, 6)), Location("/tmp/other.my", rng(1, 2, 4))]
        refs = references_at(PATH, SOURCE, 5, 11, resolver=lambda n: extra)
        self.assertEqual(len(refs), 4)
        self.assertEqual(refs[-1], extra[1])


class TestCompletion(unittest.TestCase):
    SOURCE = ("struct P { x: int }\nenum E { A, B }\nfun get(p: P) -> int {\n    return p.x\n}\n"
              "fun main() {\n    let p = P { x: 1 }\n    print(p.x)\n}\n")

    def labels(self, source: str, line: int, character: int) -> set[str]:
        return {c.label for c in completions(PATH, source, line, character)}

    def test_members_after_a_dot(self):
        self.assertEqual(self.labels(self.SOURCE, 7, 12), {"x", "A", "B"})

    def test_keywords_and_declarations_elsewhere(self):
        labels = self.labels(self.SOURCE, 6, 4)
        self.assertLessEqual({"fun", "match", "float64", "char", "P", "E", "get", "main"}, labels)
        self.assertNotIn("x", labels)

    def test_member_access_after_astral_characters(self):
        source = 'fun main() {\n    let s = "😀" + p.\n    let t = "😀" + q\n}\n'
        # just after `p.`: 20 code points, 21 UTF-16 units
        self.assertTrue(all(c.kind != "keyword" for c in completions(PATH, source, 1, 21)))
        # just before the `.` (16 code points, 17 units): not a member access
        source = 'fun main() {\n    let s = "😀" .x\n}\n'
        self.assertIn("fun", self.labels(source, 1, 17))


def _flat(symbols):
    out = []
    for s in symbols:
        out.append(s)
        out.extend(_flat(s.children))
    return out


if __name__ == "__main__":
    unittest.main()
