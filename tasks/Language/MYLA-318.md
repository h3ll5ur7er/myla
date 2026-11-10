---
id: MYLA-318
title: "Small language gaps from Advent of Code"
type: improvement
status: done
priority: low
labels: [language, stdlib]
---
Found by Advent of Code ([[Project/AoC-2015-2021]], F9). None of these blocked anything. Each cost lines in many solutions. The counts are grep-based across the 175 solutions, so they're approximate. The messages are from master `d5d80bc`.

| Gap | How often | Today |
| --- | --- | --- |
| `for c in s` over a `str` | up to 66 `while` loops | "`for ... in` requires a list or map, found 'str'"; `for c in s.chars()` works, at the cost of a list |
| A list of n equal values | about 51 push loops | no function; a candidate for the roadmap's list helpers |
| A set type | 37 `[K: bool]` maps | on [[Project/Standard-library-roadmap]] |
| A map lookup with a default | 14 of 29 uses of `get` | `get(m, k)` gives an `Option`; `m.get_or(k, d)` or `get(m, k) ?? d` |
| `parse_int` always needs unwrapping | 12 uses | wants a `?`-able `Result` with a reason, or an `unwrap_or` on `Option` |
| `<` on strings | 1 helper, `str_less` | "comparison requires numeric or char operands"; byte-wise ordering would do |
| `'p' - 'a'` | rare | "operator '-' requires integer operands"; `s[i] - 'a'` works, as the literal fits a byte there |
| `#test` on generic functions | every generic helper | excluded by D116, and left out on purpose by [[MYLA-303]]; tested through wrappers |

- [x] `for` over a `str`: by `char` (as `chars()`) or by byte, a decision in passing (D165 (1))
- [x] `<`, `<=`, `>`, `>=` on strings (byte-wise, as `list_dir` sorts), and `str` is `Ord` (D165 (2))
- [x] `char - char` as an `int32` (and `char + int`), or the reason it stays out (D165 (3))
- [x] The library ones (a list of n values, a set, a lookup with a default, `unwrap_or`) through [[Project/Standard-library-roadmap]]: all there already, below

`#test` on generic functions stays out (D116, [[MYLA-303]]).

## Decided (D165, 2026-11-07, the owner's acceptance)

- **`for c in s` goes by `char`.** Each step is a `char`, the one `s.chars()` gives there (U+FFFD for a byte outside a well-formed UTF-8 sequence, so every string can be walked and the two agree on bad bytes). Reasons: it is what `chars()` already means and what the AoC loops do with the characters (compare with `'#'`, count letters); a byte loop has its form already, `s[i]` over `0..s.len()` (or `bytes.from_str(s)`, [[Language/Standard-library/Bytes]]); Swift, Python and Go's `range` walk characters too, Rust has no `for` over a `str` at all. By byte would have made `for c in s` and `for c in s.chars()` differ on any non-ASCII text. There is no `s.bytes()` method: std.str has none ([[Language/Standard-library/Str]]), and a list of bytes would be the cost `for c in s` avoids.
- **Strings order byte-wise**, unsigned, a prefix first: the order `list_dir` sorts in (`sorted_names` in [[lib/std/fs.my]]), and Rust's and Go's; no locale. `str` is `Ord` like the numbers and `char`, so `xs.sort()` on a `[str]` ([[MYLA-323]]) and a `Heap<str>` ([[MYLA-330]]) work. `Ord`'s `cmp` gives an `int` (-1, 0, 1); as for the other built-in types it isn't a method to call on a `str` (`5.cmp(3)` isn't one either), it is what `<` is natively: std.rt's `str_cmp`, a three-way compare against 0.
- **`c - d` is an `int32`, `c + n` and `c - n` a `char`**, with the char on the left and `n` an `int32` only. A distance is an integer and a moved char a char; D4 mixes no types, so another integer type is converted with `as int32` first (a new message says so), and two chars don't add (a message names both forms). `int32` is the type of a plain literal and of `c - d`, so `c + 1` and `c + (d - c)` need no cast. A moved char is checked as `n as char` is (D26, D98): one that isn't a Unicode scalar is the runtime error `invalid char` at the operator. The literal rule stays: a char literal of at most 127 is an integer where one is expected and beside an integer it doesn't move, so every byte idiom keeps its meaning (`s[i] - 'a'`, `'0' + d` with `d: uint8` in std.fmt and std.num, `n + 'a'`). One meaning changed: `'a' + 1` and `'a' + n` with `n: int` were the `int32` 98 and are now chars (the repository had no such use; `let k: int = 'a' + 1` is still 98).

## The library boxes

Each checked by the parity program `aoc_library_helpers` (interpreted and native):

- A list of n equal values: `list.filled(n, v)`, std.list ([[Language/Standard-library/List]]; `import std.list as list`, a `pub` function).
- A set: `Set<T>`, std.set ([[Language/Standard-library/Set]], [[MYLA-330]]), keyed by any `Eq + Hash` type ([[MYLA-313]]): `Set<(int, int)>` above.
- A lookup with a default: `m.get_or(k, d)`, std.map ([[Language/Standard-library/Map]]), implicit.
- `unwrap_or` on an `Option`: std.option ([[Language/Standard-library/Option]]), implicit: `num.parse_int(s).unwrap_or(0)`.

## Evidence

Built on 4954f20 (wave 2 merged). Tests written first: the four parity programs, the checker's cases and the corpus files failed before (`` `for ... in` requires a list or map, found 'str' ``, "comparison requires numeric or char operands", "type 'str' does not satisfy the bound 'T: Ord' required by '__list.sorted'", "operator '-' requires integer operands").

- **Checker** ([[selfhost/checker.my]]): `check_for` gives a `str` the loop variable `char`; the orderings take two strings; `str` is `Ord` among `primitive_default_trait`'s; `char_arith` types `c - d`, `c ± n` and refuses `c + d` and `c ± n` with another integer type, before `unify`, whose literal rule is unchanged.
- **Interpreter** ([[selfhost/interp.my]]): `exec_for` decodes a string as it goes (`utf8_at`, std.rt's `decode_at` in Myla over `s[i]`); the async evaluator's loop, which holds its items, takes the decoded list; a `char`-typed `+`/`-` checks and gives a `VChar`, the sum wrapped as an `int32`; strings already compared (`scmp`).
- **Native code** ([[selfhost/lower.my]], [[lib/std/rt.my]]): `for_str` holds the string as `for_list` holds a list and walks its bytes, an ASCII byte (`load8`, `< 128`) the char itself, any other through std.rt's new `str_char_at`; `<` and the others call std.rt's new `str_cmp` (eight bytes at a time while equal, then unsigned bytes) and compare with 0; `char_arith` casts to `int32`, adds or subtracts, and checks as a cast to char does (`check_scalar`, the cast's check moved into a method). Nothing per target: aarch64 and wasm32 take the same IR.

Tests:

- `test_compiler_parity` (x86-64: its 178 tests pass): new `for_over_a_string`, `for_over_a_string_async`, `string_ordering`, `char_arithmetic`, `aoc_library_helpers`, each `PINNED`, the interpreter and native code agreeing, and `test_a_char_moved_past_the_scalars_is_a_runtime_error` (past U+10FFFF, into the surrogates, below 0, the `int32` sum wrapping; the interpreter's message with the value, native code's without, the same position). `scripts/test-target.py aarch64-linux test_compiler_parity` and `wasm32-wasi`: both pass, nothing excused.
- The error corpus: [[examples/errors/type_char_plus_char.my]], [[examples/errors/type_char_plus_int64.my]], pinned (`.stderr`). (A `runtime_*.my` corpus file can't be added since the Python toolchain went: `test_selfhost_interp` asks its recordings for every one; the runtime error is the parity test above.)
- The checker's own cases, `build/myla test selfhost/checker.my`: 632/632 (four of `char_arith`, six `errors_of` programs). `test_selfhost_checker`: `unit_test_3` (`'a' + 'b'`) superseded by D165's message, `compare_strings` gone (valid now). `utf8_at` and `is_char_type` in the interpreter, `char_arith` in the lowering pass.
- `test_selfhost_interp`, `test_std_modules`, `test_error_corpus`: pass. `scripts/test.sh fast`: 643 tests, 3 failures: `test_embedded_std` and `test_installed` (the committed `selfhost/embedded_std.my`, stale until the seed commit) and `test_implicit_imports.test_test_cases` (std.time's `Result.expect` in a copied library without it), which fails on 4954f20 too.
- On 4954f20 itself, six cases of `test_selfhost_checker.test_type_errors_match_the_oracle` fail, MYLA-313's changes without a `SUPERSEDED` entry (`unit_test_76`, `unit_test_144`, `unit_test_156`, `derive_on_generic`, `derive_enum_payload`, `map_literal_key`); they fail the same here, and are left to the integration.
- The bootstrap reaches its byte-identical fixed point (13,738,036 bytes).

Measured natively (x86-64, best of five, a shared machine), the sum of the code points of a 10 MB string:

| Text | `for c in s` | `for c in s.chars()` |
| --- | --- | --- |
| ASCII (`the quick brown fox …`) | 6 ms | 34 ms |
| mixed (`größe λ π 😀 naïve café, …`) | 15 ms | 38 ms |

`chars()` also makes a 40 MB list first; the loop makes none. Interpreted (one round, ASCII): 10.9 s against 11.5 s, the evaluation of the body dominating either way.

## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]].
