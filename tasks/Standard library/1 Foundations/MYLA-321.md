---
id: MYLA-321
title: "std.str: search, split, join, trim, case, replace"
type: feature
status: review
priority: high
labels: [stdlib, strings, wave-1]
---
Wave 1 of [[Project/Standard-library-roadmap]], roadmap #1, #2, #3, #4. Methods on `str` (`impl str`), byte-wise, ASCII for case. AoC's `text.my` is the reference for what is used most ([[Project/AoC-2015-2021]]). `join` is a method of `[str]` and so lives with [[MYLA-323]]'s lists in `std.list`.

- **Owns:** `lib/std/str.my`, `docs/Language/Standard-library/Str.md`
- **Needs:** [[MYLA-319]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [x] Search: `find`, `rfind`, `find_from`, `contains`, `starts_with`, `ends_with`, `count`
- [x] Split: `split(sep)`, `splitn`, `words`, `lines` (a final `\n` gives no empty last line; `\r\n` handled)
- [x] Trim and case: `trim`, `trim_start`, `trim_end`, `strip_prefix`, `strip_suffix` (an `Option`), ASCII `to_upper`, `to_lower`, `repeat(n)`, `pad_start`, `pad_end`
- [x] Replace: `replace(from, to)`, `replacen`
- [x] Measured against a hand-written loop on a 10 MB string: within 1.5 times of it, natively
- [x] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [x] Its page below [[Language/Standard-library]], with a doc block that runs

## Done (2026-11-07)

- `lib/std/str.my` has the 23 methods in one `impl str`, each with `#test` cases, and private helpers with cases of their own. The signatures and the rules for empty patterns, whitespace and widths are on [[Language/Standard-library/Str]]. Four test functions check what a value can't: split and join round-trip, `count` is the number of places `replace` changes, any bytes (a lone lead byte, `0xFF`, a match inside a character) are cut without an error, and trims compose.
- The tests came first: with stub bodies 25 of 110 cases passed (those whose stub happened to be right). Now `myla test lib/std/str.my --stdlib lib` passes 134/134, and 134/134 with `--native`. `test_std_modules` and `test_doc_blocks` pass.
- No name was taken: `contains` is a builtin method of maps only, and D151 reserves a name on its own kind. `replace` takes `old` and `new` where Rust has `from` and `to`, since `from` is a keyword.
- Choices where Rust, Go and Python differ: an empty separator splits into characters (Go; Rust gives empty pieces at both ends); an empty pattern in `replace` and `count` matches before every character and at the end (Rust and Python); whitespace is C's `isspace`, `\v` included (Python and Go; Rust leaves it out). `std.char`'s `is_space` ([[MYLA-322]]) should match. The pad width counts characters, as a format spec's width does.
- Measured natively on a 10 MB text (10,000,038 bytes; the best of 5 rounds, and three runs gave the same): `find` of a word at the end 9 ms against 13 to 14 ms for a hand-written loop (the std one checks the first byte before the rest); `split(",")` into 238,097 pieces 15 ms against 14 ms for a hand-written loop with `StringBuilder.append(s, a, b)`, 1.07 times.
- The doc block is a `myla fragment` for now: `import std.str` doesn't parse, because `str` is a keyword token and an import path takes only identifiers (`import_path` in `selfhost/parser.my`). The block's output was checked by importing a copy of the module under another name, interpreted and natively. It becomes a plain `myla` block when the parser takes `str` as a path segment, which [[MYLA-320]] needs anyway. `std.char` and `std.int` aren't affected: `char` and `int` are identifiers.
- Found on the way: natively, `assert(cond, msg)` with a message that isn't a literal (`f"…"`, `"x" + t`, a variable) fails the IR verifier, "drop of $N (__temp), which holds no value". The interpreter runs it. The test functions here use literal messages.

## Evidence

The last box was done already: [[Language/Standard-library/Str]] exists, and commit `7c5a90e` (2026-11-07, once [[MYLA-320]] made std.str implicit) turned its block from a `myla fragment` into a plain `myla` block, with no import, that `tests.burn.test_doc_blocks` runs. Checked on 7b328dd (round 3): the block, run on its own, prints its `// output:` (`NAME.. 1: Ada`, `LANGS. 2: myla`, `a++b`, `1.2`) with `build/myla run` and as a native build; `python3 -m unittest tests.burn.test_doc_blocks` passes. The note above on the fragment and `import std.str` is history: an import path takes `str` as a segment since MYLA-320.
