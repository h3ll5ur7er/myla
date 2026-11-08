---
id: MYLA-341
title: "std.text: a scanner and text layout"
type: feature
status: review
priority: medium
labels: [stdlib, strings, parsing, wave-3]
---
Wave 3 of [[Project/Standard-library-roadmap]], roadmap #8, #9. What hand-written parsers and reports need beyond `split`.

- **Owns:** `lib/std/text.my`, `docs/Language/Standard-library/Text.md`
- **Needs:** [[MYLA-321]], [[MYLA-322]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [x] `Scanner`: `peek`, `next`, `take_while`, `skip_space`, `expect`, `int`, `ident`, the position for errors
- [x] `ints(line)`: every integer in a line, signs included
- [x] Word wrap, aligned columns, indent and dedent
- [x] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [x] Its page below [[Language/Standard-library]], with a doc block that runs

## Evidence

Built on `1dd86a6`. The module is [[lib/std/text.my]], its page [[Language/Standard-library/Text]].

- **Tests first:** with the cases written and the bodies stubbed, 108 of the module's cases failed; with the bodies, all pass.
- **Cases:** 144 (140 `#test` cases and 4 test functions), all the module's own. `build/myla test lib/std/text.my --stdlib lib`: 144/144 interpreted, 144/144 with `--native`, 144/144 with `--target aarch64-linux` (qemu). With `--target wasm32-wasi` (node) every case passes but the three that expect a panic (`ints #17`, `longs #4`, `wrap #10`), which stop the run there (MYLA-370); run by group with `--only`, the other 141 pass.
- **After `scripts/bootstrap.sh`:** `python3 -m unittest tests.burn.test_std_modules tests.burn.test_doc_blocks` passes (6 tests), the page's doc block included.
- **Against Python 3.13's `textwrap`:** `dedent`, `indent` and `fill` (as `wrap(" ".join(t.split()), w, break_long_words=False, break_on_hyphens=False)`) gave the same text for 4,000 random texts each (seeds 1 and 7), natively.
- **Speed** (natively, a 10 MB text of 330,235 lines and 1,320,940 integers, best of five): `ints` over the whole text 45 ms (220 MB/s), over each line 57 ms (175 MB/s), a `Scanner` with `expect` and `long` 69 ms (146 MB/s); `s.lines()` alone 29 ms; Python's `re.findall` and `int` 505 ms (20 MB/s). Handing every number to `std.num` took `ints` 138 ms (72 MB/s); numbers of up to 9 (18) digits are now added up in place, longer ones still go to `std.num`.

Decisions, on the page:

- `sc.int()` is an `int` (`int32`), `sc.long()` an `int64`: `int64` is a keyword and can't name a method. `ints` and `longs` follow. Out of range, `int` and `long` give an `Overflow` error; `ints` and `longs` fail at run time, naming the number.
- In `ints`, a `-` before a digit is a sign unless an ASCII letter or digit comes before it: `"5-3"` is `[5, 3]`, `"x=-3"` is `[-3]`, `"1518-11-01"` is `[1518, 11, 1]`, `"a-b-123[x]"` is `[123]`.
- `ScanError { kind, pos, line, col }` (D168), with `Other(str)` for a parser's own errors through `sc.error(kind)`. `pos` is a public field: setting it back is how a parser backtracks.
- `wrap` counts bytes and never breaks a word: a longer one stands alone. `columns` counts characters, as `pad_start` does.

For the integrator: the module doesn't import `std.str`, `std.char` or `std.list`, because with any of them `--native` can't build the harness (MYLA-360). It writes out the bits of `words`, `pad_start`, `pad_end` and `join` it needs; swap them back once MYLA-360 is fixed.
