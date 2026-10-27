---
id: MYLA-84
title: The lexers disagree on non-ASCII letters in identifiers
type: bug
status: review
priority: low
labels: [lexer, selfhost, spec]
---
The Python lexer accepts any Unicode letter in an identifier (`str.isalpha`/`isalnum` in [[src/myla/lexer.py#L90-L95]]); the self-hosted lexer accepts only ASCII letters ([[selfhost/util.my#L57-L63]]), and so do [[grammar/myla.ebnf]] and the tree-sitter grammar generated from it ([[MYLA-77]]). [[Language/Lexical-structure]] only says "a letter".

```myla
fun main() {
    let größe = 1
    print(größe)
}
```

`python3 myla.py run` prints `1`; `build/myla` fails with `lex error: unexpected character 'ö'` at 2:11.

ASCII-only is simpler (no Unicode tables in the self-hosted lexer, every tool agrees with the grammar as it is), so the likely fix is to make the Python lexer reject them too.

- [x] Decide (ASCII only, or Unicode letters everywhere) and record it on [[Project/Decisions]]
- [x] Make both lexers, the grammar file and [[Language/Lexical-structure]] agree
- [x] A lexer gate case and an error-corpus file (or, for Unicode, a sample lexeme in `@sample IDENT`)

## How

Decided with the user: Unicode identifiers everywhere (D72 on [[Project/Decisions]]), together with [[MYLA-86]].

- An identifier is `_` or XID_Start, then XID_Continue, without normalization; keywords and number literals stay ASCII. `scripts/gen_unicode_tables.py` takes the non-ASCII ranges from Python's `str.isidentifier` (Unicode 15.1: 665 XID_Start and 772 XID_Continue ranges) and writes them for both lexers: `src/myla/unicode_ident.py` (tuples, bisect) and `selfhost/unicode.my` (12 hex digits per range in a `const` string, binary-searched in place, so a lookup allocates nothing). A fixed table rather than the host's `unicodedata`, so Python 3.12 and 3.13 (Unicode 15.0 and 15.1) and the self-hosted lexer agree.
- The Python lexer used `str.isalpha`/`isalnum`, which differ from XID (it rejected `℘`, combining marks and the middle dot inside a name), and `str.isdigit` for number literals, which took `١` (Arabic-Indic one) as a digit; both now follow the table and ASCII digits. The self-hosted lexer's `is_ident_start`/`is_ident_continue` delegate to `unicode.my`.
- [[grammar/myla.ebnf]] and [[Language/Grammar]]: `IDENT = ident_start ident_char*` with `/[_\p{XID_Start}]/` and `/\p{XID_Continue}/` (tree-sitter understands these, as tree-sitter-rust uses them); samples `größe` and `π`. The tree-sitter grammar is regenerated; the VS Code TextMate grammar approximates XID with Unicode general categories.
- The language server: word boundaries for completion and squiggles use the lexer's classes, type texts treat non-ASCII bytes as name characters, and semantic tokens step over `\u{…}` in f-strings (its brace isn't a hole).
- Found on the way: the self-hosted backend evaluated a `const` string made with `+` at each use, into a temporary its frame had no slot for, so a function reading such a const crashed on return (the new `unicode.my` tables are such consts). The checker now folds string `+` in consts, and the backend emits a folded `str` const as a static string.

## Evidence

- `tests/unit/test_lexer.py`, `TestUnicodeIdentifiers`: letters of four scripts and a letter number; `℘`, a combining accent, the middle dot and an Arabic-Indic digit inside names; `€`, a leading middle dot and a leading Arabic-Indic digit rejected as "unexpected character". It failed before (the Python lexer rejected `Ⅻ` and `℘`, split `e\u0301`, and took `١` for a number).
- `tests/unit/test_unicode_tables.py`: both copies of the table hold the same ranges, and they are current for the Unicode version they record (checked on Python 3.13).
- The lexer gate's new token case (identifiers and escapes) fails with the self-hosted lexer's old ASCII classes and passes now; parser-gate snippets for identifiers that may continue but not start a name; error-corpus `lex_ident_bad_start.my`.
- The tree-sitter grammar parses every source, `examples/unicode.my` included, and flags every lex error of the corpus.
- `examples/unicode.my` (Unicode names, the new escapes) prints the same in both interpreters and both native backends; its 5 `#test`s pass in both CLIs.
- Parity program `const_string_concatenation_in_functions` (both backends, the self-hosted gates): it crashed the self-hosted build before the const fix.
- A language-server scenario: definition and hover for `größe` and `日本`, with UTF-16 ranges after `😀`.
- Full run: 479 unit, 2 integration and 544 burn tests pass; the bootstrap reaches a new fixed point at 7,876,416 bytes (the tables and the escape code).
