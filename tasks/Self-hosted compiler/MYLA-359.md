---
id: MYLA-359
title: "Check time of the implicit std modules: about 26 ms for every program"
type: improvement
status: review
priority: medium
labels: [checker, performance, stdlib]
---
Found while integrating [[MYLA-320]]. With the six implicit modules (D164), `myla check` of a hello-world takes 26 ms (min of 15) instead of 0.4 ms. An AoC-sized program takes 29 ms instead of 3.3 ms, while `selfhost/main` doesn't change measurably. Their `#test` cases are already skipped unparsed outside `myla test` of the module itself. What remains is checking the method bodies, two thirds of it `std.int` (one impl per width, 4,375 lines). Measured with only one module loaded, before the cases were skipped: str 3.5 ms, char 2.3, int 23.2, list 6.8, option 2.5, map 1.4. The language server and `myla run` pay this on every check.

Options, cheapest first:

1. A smaller `std.int`: the operations that are the same for every width written once over a bound, if the bounds can carry them, or the generator emitting less.
2. Checking a method's body only when the program calls it, or caching the result for the embedded library, whose text is fixed per build.

- [x] std.hash's checksums (FNV-1a, CRC-32, Adler-32) moved to a module of their own, imported as any other (D166): std.hash keeps the `Hasher` and the `Hash` impls
- [x] A profile of hello-world's check with the seven modules
- [ ] The cheapest fix that brings it under 5 ms, measured (halved, 44.4 → 21.6 ms; not under 5 ms: see "What is left")

## The profile

Callgrind on `build/myla check` of a hello world (`fun main() { print("hello") }`, no import) at 7b328dd: 206.7 M instructions, of which 1.6 M without the implicit modules (their files emptied). With `from std.io import println` (a "hello" importing std.io): 281.4 M, 73.5 M without them. Of the hello's 279 M after [[MYLA-396]]: lexing 113 M (40 %), parsing 63 M (23 %), renaming 15 M (5 %), checking 82 M (29 %, 707 bodies). By module (the difference with the module's file emptied): std.int 107 M, std.list about 33 M, std.hash 30 M, std.str 12.5 M, std.option 9.9 M, std.map 7.0 M, std.char 4.9 M. The lexer took 430 instructions a byte; std.int's 158 KB were 66 KB of `#test` cases (2,042), which the parser skipped but the lexer still made tokens of: removing the case lines from the files cut 40.7 M (14.6 %), removing the comments too only 3.6 M more. Hot spots: `keyword_kind` comparing each identifier with all 39 keywords (12.9 M, 4.6 %), one-character operators' lexemes made by `cp_utf8` (9.4 M), the lexer's `peek`/`advance` method calls per character (not inlined), the parser's expression levels each copying their first token, strings and all (`peek`, 50 instructions a call).

## What changed

Each a commit of its own, measured on its own:

1. **The lexer skips an imported module's cases** ([[selfhost/lexer.my]] `skip_test_attr`, `lex_with`): in every module but the entry (the loader's `skip_tests`, [[MYLA-396]]) a `#test` attribute and its `(…)`/`[…]` are consumed unlexed, over nested brackets, strings, chars, f-strings with their holes, and comments; where the brackets don't close the lexer goes back and lexes them as before, so the error is the same. The parser's skip stays for anything the lexer leaves.
2. **The checker checks an implicit module's body only once it is called** ([[selfhost/checker.my]] `run_all`, `lazy_decls`, `called`): the functions of the implicit modules and the methods of their impls of no trait wait; `called` records each callee by its checked name at a call (`infer_call`), a method call (`infer_method_call`), a type's function (`infer_static_call`), a function used as a value and a partial application, and the waiting bodies are checked in rounds until none left is called. Trait impls (operators, bounds, `for`, derives and `Hash` call them unnamed) are checked as before, and so is every body when the entry is the module itself (`myla test lib/std/int.my`). The loader marks the implicit modules' functions in `std_impls` too. A hello world checks 205 bodies instead of 707.
3. **Keywords by their first byte, operators' text a literal** ([[selfhost/tokens.my]] `keyword_kind`, `one_char_text`).
4. **std.checksum** (D166): FNV-1a, CRC-32 and Adler-32 with their cases and test functions moved from std.hash to `lib/std/checksum.my` (32 cases); std.hash keeps the `Hasher`, the `Hash` impls and wyhash (65 cases; 95 before, two test functions split in two). std.archive and `tests/burn/test_archive.py` import it; std.compress's comment and pages updated; a page [[Language/Standard-library/Checksum]], [[Language/Standard-library/Hash]] and the index changed.
5. **Lexer and parser hot loops**: blanks, names and line comments are one loop over the code points instead of a `peek`/`advance` call per character; the expression levels take their start with `peek_pos` (a line and a column) instead of copying the token (`mk_expr_at`).

## Decisions (proposals)

- **Lazy checking of the implicit modules' bodies.** A type error in a body of std.str, std.int, … that the program doesn't call is no longer an error of the program: only `myla test` (or `check`) of the module's own file, which CI runs, reports it. Alternatives: check every body (as before, 22 ms more per program); check lazily only with the embedded library, whose text is fixed per build, and everything with `--stdlib`/`MYLA_STDLIB` (a library being edited). I recommend the first: the library's own tests check every body, and `MYLA_STDLIB` is how a library is edited, but its author runs `myla test` on the module.
- **The module's name, `std.checksum`**, and FNV-1a in it as D166 lists, though it is a hash, not a checksum. Alternatives: `std.crc`; FNV-1a staying in std.hash beside wyhash (2 KB more for every program). I recommend as built.

## What is left

After the five, the hello world's 100.9 M instructions are lexing 42.0 M (42 %), parsing 35.1 M (35 %), renaming 9.8 M (10 %) and checking 10.9 M (11 %): the cost is reading the implicit modules, now that checking them is mostly gone, and std.int is half of it (55 M of the 110 M the seven modules add to a program importing std.io). Under 5 ms needs the bodies not to be read at all. In order of what I would try:

1. **Lazy bodies**: in an implicit module, the lexer skips a function's or method's body `{…}` (the skip of item 1, keyed on the `{` after a `fun`'s signature) and the parser keeps its text and position; the checker lexes and parses it, with fresh node ids from the loader's spans, when `called` first names it. That leaves the signatures, perhaps a fifth of the text: an estimated 70 M of the 100 M.
2. **A cache of the embedded library**: the loaded and renamed declarations of the seven modules serialized at build time (`scripts/bootstrap.sh` already generates `selfhost/embedded_std.my`), read instead of parsed when the library is the embedded one.
3. **A smaller std.int**: its eight impls, 580 lines each, are generated (`scripts/gen_std_int.py`); the operations that are the same for every width written once over a bound would need bounds that carry integer operators and literals.

## Evidence

- **Tests first**:
  - Item 1: `tests/burn/test_imported_cases.py`'s `test_an_imported_module_s_cases_are_not_parsed` got a second function whose case has a lex error (`#test("@", 1 @ 2)[f"{")"}"] // a name`): with the compiler before (`myla-396b`) the program importing it fails, `lex error: unexpected character '@'` in the imported file; after it passes, and the module's own `myla test` still reports the lex error. The lexer's new cases (`skip_test_attr` ×5, `skip_group` ×2, `lex_with`, `one_char_text` ×3, `lexer_on`) pass: `myla test selfhost/lexer.my` 69/69.
  - Item 2: `tests/burn/test_implicit_imports.py`'s new `test_their_bodies_are_checked_once_called` (a fixture std.int with an ill-typed method, a method calling it and an ill-typed function: a program calling none runs, one calling any of them through a method, a call, a function value is the type error located in std.int) failed before (`('', 'type error: return type mismatch: …', 1) != ('42\n', '', 0)`) and passes after.
  - Item 3: `keyword_kind`'s cases 3 → 9 (keywords of each first letter, `typealiases`, `lets`, `zip`); the edit was checked to keep all 39 keywords. `myla test selfhost/tokens.my` 21/21.
  - Item 4: `myla test lib/std/checksum.my` 32/32 and `lib/std/hash.my` 65/65, interpreted and `--native`; std.archive 83/83, std.compress 136/136 both ways.
- **Instructions** (callgrind, `build/myla check`; base 7b328dd, then after MYLA-396, then after each item):

| Program | base | MYLA-396 | 1 lexer skip | 2 lazy check | 3 keywords | 4 std.checksum | 5 hot loops |
| --- | --- | --- | --- | --- | --- | --- | --- |
| hello world, no import | 206.7 M | 206.3 M | 173.3 M | 129.6 M | 119.9 M | 112.0 M | 100.9 M |
| hello world with std.io | 281.4 M | 278.8 M | 243.3 M | 198.2 M | 184.7 M | 176.9 M | 161.3 M |
| `examples/maps.my` | 211.5 M | 211.0 M | 178.0 M | 134.5 M | 124.5 M | 116.6 M | 105.1 M |

- **Time** (CPU time of `build/myla check`, min of 21 runs, the compilers alternating, embedded library):

| Program | base | MYLA-396 | 1 | 2 | 3 | 4 | 5 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| hello world, no import | 44.4 ms | 44.7 | 38.6 | 29.3 | 27.7 | 25.2 | 23.7 → **21.6** |
| hello world with std.io | 60.3 ms | 61.6 | 55.0 | 43.1 | 41.9 | 39.9 | 39.1 → **37.2** |
| `examples/maps.my` | 44.8 ms | 45.2 | 39.0 | 29.4 | 27.2 | 26.7 | 25.9 → **23.0** |
| `examples/strings.my` | 45.9 ms | 45.8 | 40.2 | 30.2 | 28.9 | 26.3 | 25.8 → **23.7** |
| a hello world importing std.compress | 82.2 ms | 84.4 | 76.2 | 65.0 | 62.1 | 60.2 | 58.9 → **55.6** |
| importing std.int, bitset, bigint, text, http, compress | 168.2 ms | 158.3 | 148.2 | 137.8 | 133.8 | 131.5 | 128.4 → **121.7** |

(Column 5 shows its two halves, the lexer loops and then `peek_pos`.) `check selfhost/main.my`, min of 5: 722.7 → 593.6 ms. The machine is a shared 4-CPU container, 2.1 GHz; the task's 26 ms was measured on another.

- `scripts/bootstrap.sh` after each: byte-identical fixed point (18,892,652 bytes at the end).
- Suites (after items 1 and 2): `scripts/test.sh fast` 765 tests, only `test_embedded_std` failing (expected until the seed commit); `python3 -m unittest tests.burn.test_compiler_parity tests.burn.test_selfhost_cases tests.burn.test_error_corpus tests.burn.test_selfhost_checker tests.burn.test_lsp tests.burn.test_std_modules tests.burn.test_implicit_imports tests.burn.test_imported_cases tests.burn.test_doc_blocks tests.burn.test_examples_run` 769 tests OK. After item 4: `test_doc_blocks`, `test_archive`, `test_compress`, `test_std_modules`, `test_implicit_imports`, `test_lsp` 194 tests OK. At the end (all five): `scripts/test.sh fast` 765 tests, only `test_embedded_std` failing; the slow suites above with `test_archive`, `test_compress`, `test_selfhost_lexer` and `test_selfhost_parser`, 790 tests OK (202 skipped).

## Comments

- 2026-11-09, [[MYLA-376]]: `std.int`'s new `count_ones`, `leading_zeros` and `trailing_zeros` on eight widths add 2–3 ms to every program's check (a hello world 43.8 → 48.3 ms); and a std module importing `std.int` explicitly parses its 2,042 cases ([[MYLA-396]]). `std.hash`'s CRC-32 and Adler-32 take a whole list and rebuild the CRC table on every call, so `std.compress` keeps its own: a version over a range of a list would let it use them (gunzip of 100 MB went 526 → 802 ms through a slice).
