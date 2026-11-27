---
id: MYLA-359
title: "Check time of the implicit std modules: about 26 ms for every program"
type: improvement
status: done
priority: medium
labels: [checker, performance, stdlib]
---
Found while integrating [[MYLA-320]]. With the six implicit modules (D164), `myla check` of a hello-world takes 26 ms (min of 15) instead of 0.4 ms. An AoC-sized program takes 29 ms instead of 3.3 ms, while `selfhost/main` doesn't change measurably. Their `#test` cases are already skipped unparsed outside `myla test` of the module itself. What remains is checking the method bodies, two thirds of it `std.int` (one impl per width, 4,375 lines). Measured with only one module loaded, before the cases were skipped: str 3.5 ms, char 2.3, int 23.2, list 6.8, option 2.5, map 1.4. The language server and `myla run` pay this on every check.

Options, cheapest first:

1. A smaller `std.int`: the operations that are the same for every width written once over a bound, if the bounds can carry them, or the generator emitting less.
2. Checking a method's body only when the program calls it, or caching the result for the embedded library, whose text is fixed per build.

- [x] std.hash's checksums (FNV-1a, CRC-32, Adler-32) moved to a module of their own, imported as any other (D166): std.hash keeps the `Hasher` and the `Hash` impls
- [x] A profile of hello-world's check with the seven modules
- [x] The cheapest fix that brings it under 5 ms, measured (halved, 44.4 → 21.6 ms in round 3; in round 4 the bodies read only once called, 100.7 → 39.4 M instructions, 26.1 → 10.0 ms on the busier container: not under 5 ms, see "Round 4: what is left", [[MYLA-412]]) — not reached here: 6.1 ms and 21.2 M instructions on `547339a`; carried over to [[MYLA-552]] (review 2026-11-12)

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

## Round 4: the bodies read once called

The first proposal of "What is left", built:

- **The lexer skips a body** ([[selfhost/lexer.my]] `lex_lazy`, `body_ahead`, `skip_body`): in an implicit module, at a `{` whose tokens back to a `fun` are its signature, the body is consumed to its `}` unlexed and only the two braces are emitted (the `{` with its code point offset and the suffix `body`, the `}` with the offset past it). The skip (`skip_group`, which `#test` attributes use too) is now one loop over the code points with locals, matching each bracket with its own closer over strings, chars, f-strings with their holes and comments; where a bracket doesn't close or closes another, or a string doesn't end, the lexer goes back and lexes the text as before.
- **The parser keeps it** ([[selfhost/parser.my]] `fun_body`, `BodySite`, `parse_source_lazy`, `parse_body`, `body_ids`): an empty block of its place, and a site with node ids kept for it (twice its code points and 8: every body of the corpus needs well under half that, and `parse_body` refuses with an internal error past them), so its nodes are in its module's range of ids and `file_of`, the debugger's line tables and the error reports find its file. `lex_part` lexes the body later from its place in the file's code points, `parse_body` parses it with the kept ids.
- **The loader** ([[selfhost/loader.my]] `implicit_files`, `Loader.lazy`, `parse_module`, `LazyTable`, `kind_of`) knows the implicit modules' files before it loads the entry, so a module imported explicitly too is read lazily, keeps each module's renamer and code points, and hands the checker `Loaded.bodies` (`LazyBodies`), whose `parse` reads a body and renames it with the names in scope there. Its lex, parse or module error is reported with its kind (`kind_of` in `type_errors`) at its place.
- **The checker** ([[selfhost/checker.my]] `with_body`, `put_bodies`, `build_checker_lazy`) reads a body the first time `check_body` checks it (a trait impl's at once, as before, a lazily checked one once `called` names it), and puts every body read into `decls`, `functions`, `methods` and `method_decls` before `fill_in`, so the interpreter, the native lowering and the REPL see it. Every tool that loads a program (driver, `gen_main`, `interp_main`, `play_main`, the REPL, the language server) calls `build_checker_lazy`.
- The language server's go-to-definition and outline parse a file on their own, whole (`tools/lsp/resolve.my`, `symbols.my`), so a definition in an implicit module's body is found as before; its diagnostics go through the loader and report a late body's error with its kind. `myla test lib/std/int.my` (an entry of `std`, no implicit modules) parses everything.
- Then the keys: `body_key` is one `int64` (the declaration's id, the line below 2^20, the column below 2^12; the lexer leaves a body past them unskipped) instead of a formatted string, and the loader matches the sites with the functions in order instead of through a map of places.

### Decisions (proposals)

- **Lazy parsing with any library**, the embedded one and `--stdlib`/`MYLA_STDLIB` alike, as the lazy checking the owner accepted: a lex or parse error in an implicit module's body that the program doesn't call is no longer the program's error; `myla test` of the module, which parses the whole file, reports it. Alternatives: parse lazily only with the embedded library (fixed per build, known to parse) and the whole text with a library being edited; parse every body as before. I recommend as built: the same rule as the checking, and the module's own tests read everything.
- **Node ids kept at parse time** rather than fresh ids at check time: no new span entries, the reports, `file_of` and the debug line tables are unchanged; the cost is gaps in the id numbers (an `int32`; the seven modules keep a few hundred thousand). Alternative: fresh ids past the prelude's, with spans the checker adds and every consumer of `Loaded.spans` reads.
- The errors of a late body are carried as checker errors whose message starts with their kind (`parse error: …`), rather than a new field of `CheckErr`, which is built in hundreds of places.

### Round 4: what is left

The hello world's 39.4 M instructions (1.8 M and 1.2 ms without the implicit modules): lexing the seven modules 16.8 M (decoding their 300 KB to code points 2.5 M, the skipped bodies and cases 4 M, the signatures, comments and other declarations the rest), parsing the signatures 3.7 M, renaming 1.9 M, recording the bodies left 1.4 M, checking 14.1 M (registering the 1,100 methods' signatures, `resolve_impls`, 4.9 M; the 205 bodies a hello world checks 4.8 M, 2.7 M of it reading them). Reading the signatures is now most of it, so lazy bodies are not enough for 5 ms: the build-time cache of the embedded library, the second proposal, is worth a task ([[MYLA-412]]); it would take out lexing, parsing and renaming, an estimated 39 → 20 M with the reading of the cache. A program importing std.io pays 100.0 M, 60 M of it std.io and its imports parsed and checked whole: [[MYLA-413]] proposes their bodies read and checked once called too.

### Round 4: evidence

- **Tests first**: `tests/burn/test_implicit_imports.py`'s new `test_their_bodies_are_parsed_once_called` (a fixture std.int with a parse error, a lex error and a type error each in a method's body and a parse error in a function's): a program calling none runs and checks, one calling each reports that error, with its kind, at its exact `file:line:col`, and the module's own `myla test` reports the first error of the file. Before (the round-3 compiler) a program not calling them failed at once: `parse error: expected variable name, found '='` at `int.my:4644:13`; after it prints `42`, and calling it gives the same error at the same place. `tests/burn/test_selfhost_parser.py`'s new `test_bodies_read_later_are_the_same` runs `parse_main --lazy` on every file of the parser corpus and of `lib/std/**`: the tokens of each body lexed on its own (`lex_part`) are the file's, with their places, and the tree with the bodies parsed later is the whole file's (the names made up from node ids aside), for more than 5,000 bodies; of the error corpus only `parse_several_errors.my` is left out (the signatures' errors come before the bodies'). New cases (lexer 86/86, parser 183/183 in all): lexer (`body_ahead` ×4, `skip_body` ×2, `skip_group` ×6, `lex_lazy` ×4, `lex_part` ×2, `lexed`), parser (`fun_body` ×2, `parse_source_lazy` ×2, `parse_body` ×3, `body_ids` ×2, `lazy_parser_on`), checker `with_body`, `put_bodies`, `body_key` ×2, `no_body`, loader `kind_of` ×2, `parse_main` 4.
- **Instructions** (callgrind, `build/myla check`, embedded library; round 3's end, then the lazy bodies, the one-loop skip, the integer keys):

| Program | round 3 | lazy bodies | one-loop skip | integer keys |
| --- | --- | --- | --- | --- |
| hello world, no import | 100.7 M | 45.7 M | 41.3 M | **39.4 M** |
| hello world with std.io | 161.1 M | 106.5 M | 101.9 M | **100.0 M** |
| `examples/maps.my` | 105.0 M | 50.1 M | 45.7 M | **43.8 M** |
| `examples/strings.my` | 104.8 M | 49.8 M | 45.4 M | **43.5 M** |
| `check selfhost/main.my` | 3,038.6 M | | | **2,972.4 M** |

- **Time** (CPU time of `build/myla check`, min of 21 runs, the four compilers alternating; the container was busier than in round 3, load average 3, so round 3's end measures 26.1 ms here where it measured 21.6):

| Program | round 3 | lazy bodies | one-loop skip | integer keys |
| --- | --- | --- | --- | --- |
| hello world, no import | 26.1 ms | 10.7 | 10.2 | **10.0** |
| hello world with std.io | 40.8 ms | 25.5 | 24.5 | **24.5** |
| `examples/maps.my` | 27.6 ms | 11.9 | 11.2 | **11.0** |
| `examples/strings.my` | 27.7 ms | 11.8 | 11.2 | **11.0** |

`check selfhost/main.my`, min of 5: 684.7 → 687.1 ms (no change measurable; 2 % fewer instructions).
- `scripts/bootstrap.sh`: byte-identical fixed point (19,462,378 bytes).
- Suites: `scripts/test.sh fast` 771 tests OK (3 skipped; `test_embedded_std` passes, as `lib/` is unchanged); `python3 -m unittest tests.burn.test_compiler_parity tests.burn.test_selfhost_cases tests.burn.test_error_corpus tests.burn.test_selfhost_checker tests.burn.test_lsp tests.burn.test_std_modules tests.burn.test_implicit_imports tests.burn.test_imported_cases tests.burn.test_doc_blocks tests.burn.test_examples_run tests.burn.test_selfhost_lexer tests.burn.test_selfhost_parser` 791 tests OK (206 skipped).

## Comments

- 2026-11-09, [[MYLA-376]]: `std.int`'s new `count_ones`, `leading_zeros` and `trailing_zeros` on eight widths add 2–3 ms to every program's check (a hello world 43.8 → 48.3 ms); and a std module importing `std.int` explicitly parses its 2,042 cases ([[MYLA-396]]; 1,826 since [[MYLA-395]]). `std.hash`'s CRC-32 and Adler-32 take a whole list and rebuild the CRC table on every call, so `std.compress` keeps its own: a version over a range of a list would let it use them (gunzip of 100 MB went 526 → 802 ms through a slice).
- 2026-11-09: the owner accepted the proposals: an implicit module's bodies checked once called (an error in a body no program calls is reported by `myla test` of the module), and `std.checksum` with FNV-1a in it.

## Review 2026-11-10

Not ready ([[Project/Review-2026-11-10]]): lazy parsing can load a different program without an error: a missing `}` swallows the methods after it (Z1), `body_key` collides (Z2), and `myla build` of a file without `main` builds a program that does nothing (Z3, [[MYLA-415]]). "Under 5 ms" moves to [[MYLA-412]]. The fix is in [[MYLA-416]].

- [x] The review's blocker, fixed with [[MYLA-416]]: Z1 (a skipped body stops at a line that starts with a declaration's keyword), Z2 (a body keyed by its `{`), Z4, the marker of an unread body with compiling one an internal error, the skipper's mutants and `scripts/update-seed.sh` checking the implicit modules whole. Z3's other half (`sig_of`'s fallback, a file without `main`) is [[MYLA-415]]'s. Evidence in [[MYLA-416]].

## Round 5's follow-up: the parse the toolchain carries

[[MYLA-412]] (2026-11-11): every module of `std` but std.rt is read from a parse written when the toolchain is built, wherever its text is the embedded one (the implicit modules' bodies parsed too). A hello world's check 40.7 → 20.9 M instructions, CPU time 9.1 → 5.8 ms (median of 31; min 8.4 → 5.3) on the shared container: not under 5 ms, so the last box stays open. What is left is mostly the checker's: registering the implicit modules' methods (`resolve_impls` 5.0 M), checking the 205 bodies (4.3 M), the globals, derives and signatures (2.8 M); and renaming the signatures (2.5 M). See MYLA-412's "What is left".

## Review 2026-11-12

Signed off in [[Project/Review-2026-11-12]], with a follow-up in [[MYLA-552]]: a hello world checks in 21.2 M instructions and 6.1 ms on `547339a` (39.4 M and 8.7 ms before round 5); the last box, under 5 ms, moves there.

## Round 6 ([[MYLA-552]])

The reason it stays near 6 ms, measured on `dafd287` (20.7 M instructions): a third of the time is the kernel's, a page fault for each 4 KB of the 4.1 MB of fresh heap the check touches (1,109 faults, about 2.1 ms of system time); the instructions take about 4 ms. Huge pages for the heap bring the faults to 90 and the check under 5 ms, at 0.2 ms more for every small program with tasks: [[MYLA-608]] proposes them for the toolchain only.

## Round 6's follow-up ([[MYLA-608]])

Under 5 ms: the toolchain asks for huge pages for its heap at its start (std.rt's `heap_huge_pages`), so the check's 4 MB of fresh heap faults 2 MiB at a time. A hello world's `myla check` (`MYLA_THREADS=1`, 200 runs from a shell loop as above, the binaries alternating, four rounds): before 5.05, 5.72, 5.09, 5.24 ms, after 4.16, 3.81, 4.13, 4.45 ms; minor faults 1,199 → 179; instructions unchanged (20,701,695 → 20,701,739). Programs `myla build` builds don't ask and are unchanged. Evidence in [[MYLA-608]].
