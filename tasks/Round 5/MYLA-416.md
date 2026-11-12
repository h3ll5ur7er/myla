---
id: MYLA-416
title: "P3a Lexer and parser: lazy skipping, f-string holes, D186"
type: bug
status: review
priority: high
labels: [lexer, parser, lazy-parsing, round-5]
---
Work package P3 of [[Project/Review-2026-11-09]], the lexer and parser half that [[Project/Review-2026-11-10]] §5 splits off (wave A1). Files: `selfhost/lexer.my`, `selfhost/parser.my`, the loader's lazy entry points. Reopens [[MYLA-373]] and [[MYLA-359]].

- [x] Z1: a method with a missing `}` can't swallow the methods after it: fall back to eager lexing when a skipped body holds a declaration keyword at the start of a line
- [x] Z2: `body_key` packs the place the limit tests (the `{`), not the `fun` keyword's
- [x] Z4: a `#test(…)[…]` is skipped only where an attribute may stand
- [x] D179: an unread body carries a marker instead of an empty block (the back-end side is [[MYLA-415]])
- [x] The skipper's three surviving mutants get tests: an `f` before a `"` taken for an f-string, braces in an f-string hole, the `}` token's column
- [x] `scripts/update-seed.sh` checks the seven implicit modules whole (D179)
- [x] M1 and D186: each f-string hole parsed on its own; `a < b, c > (d)` one generic call only in a call's argument list; list, map and tuple literals read comparisons
- [x] D186: a budget for the look-ahead (32,000 comparisons in a list: 25 s)
- [x] M14: an imported module's `#test` case with unbalanced brackets gives the right error, at the case

## Evidence

Commits on `worktree-agent-ad519a00c8e57d5c2` (no staging commit, no seed): `MYLA-416: lazy skipping can't load a different program (Z1, Z2, Z4, D179's marker)`, `MYLA-416: D186's type-argument scan, f-string holes on their own, M14`, and the closing one (the marker's case in `lower.my`, the grammar's comment, the tasks).

- **Z1** ([[selfhost/lexer.my]], `skip_group`, `starts_decl`): a line of a skipped body that starts with `fun`, `pub`, `struct`, `enum`, `impl`, `trait`, `actor`, `typealias`, `const`, `import`, `from` or `async fun` ends the skip, and the body is lexed as before. Before (`test_a_body_without_its_brace_keeps_the_methods_after_it`, the review's `bug2_missing_brace.sh`): (a) `expected '}' to close impl block, found ''` at the end of the file; (b) with one more `}`, no error, `type 'int32' has no method 'q4_after'`, and `stage3 gen_main.my` against that library exit 0. After: `parse error: expected an expression, found 'fun'` at `int.my:4650:5`, the eager error and place, in `check` and `run` of a program calling either method, and compiling the compiler against it fails with it. Lexer cases: `skip_group` #7, #8, `lazy_shape` #5, `starts_decl_at`, `word_at`, `decl_initial`.
- **Z2** ([[selfhost/checker.my]] `unread_key`, [[selfhost/loader.my]] `add_fun`): the key is the place of the body's `{`. Before (`test_a_signature_over_two_lines_keeps_its_body`, `bug1_key_collision.sh`): `2 2` interpreted and native; after: `1 2`.
- **Z4** (`attribute_may_stand`): before (`test_a_test_attribute_is_skipped_only_where_one_may_stand`, `bug4_test_attr_in_body.sh`): `check main.my` exit 0 and `run` printed 1; after: `lex error: unexpected character '@'` at `m.my:2:33`, as `check m.my` gives. A body read late is lexed with `skip_tests` as the module read whole (`lex_part`'s case; the test's `with_case`: 5).
- **D179's marker** ([[selfhost/ast.my]] `unread_block`, `is_unread_body`): a block without statements at its `{` whose range is empty there, which no parsed block (its range covers its braces) or made-up one (no place) is; the checker replaces only a marker (`with_body`, `read_into` through `unread_key`), and `lower_function` refuses one (`Err("its body was never read")`, its case #2), which `take_ir` reports as an internal error. The review's `bug3_no_main.sh`: `myla build` of a file without `main` exited 0; now `internal error: main can't be lowered to the IR: its body was never read`, exit 1 (the clean error is [[MYLA-415]]'s).
- **The three mutants**, each applied by hand to a copy of `selfhost/` and caught by `myla test selfhost/lexer.my`: the `f` that ends a name taken for an f-string's (`lazy_shape` #6), a hole's `{` not counted (`lazy_shape` #8, `hole_end` #2), the `}` token's column off by one (`body_braces` #1 to #3).
- **`scripts/update-seed.sh`** runs `myla check lib/std/<m>.my --stdlib lib` for the seven implicit modules after the bootstrap and stops on a failure: tried by hand on `lib/` (all seven check) and on a copy with a broken `int.my` body (`FAIL: lib/std/int.my doesn't check as a whole`, exit 1); not run (the seed is the integrator's). `parse_main --lazy` prints `same error` where both reads fail, and `test_bodies_read_later_are_the_same` holds a `lib/std` file to reading without one (`test_a_std_file_with_an_error_fails_the_comparison`). [[Development/Conventions]] tells library editors to `myla test` the module they changed.
- **M1 and D186** ([[selfhost/parser.my]], `Parser.elems`, `type_args_then`; [[selfhost/lexer.my]], `scan_fstring`, `scan_fstring_hole`): before, `bug_fstring_holes.my` and `bug_fstring_holes2.my` gave `format() has 2 placeholder(s) but 1 argument(s)` and the parity program `comparisons_in_literals_and_holes` `cannot call a value of type 'int32'`; after, `true true`, `below: false, above: false`, `false5 > (9)`, ` false and true`, and the parity program prints the same natively and interpreted (pinned). A hole whose brackets don't close in it is a lex error (`lex_fstring_hole_unclosed`, `lex_fstring_hole_unmatched`, pinned `.stderr`). `reg_list.my`'s `both(a < p.x, c > (d))` stays one generic call, as D186 says of a call's arguments.
- **The budget** (`TYPE_ARGS_BUDGET`, 128 tokens): 32,000 `x < y` in a list 13.25 s before, 0.14 s after; in a call's arguments 13.39 s before, 0.12 s after (`test_a_long_run_of_comparisons_parses_in_linear_time`, under 5 s).
- **M14** (`case_closes`): `bug8_imported_broken_case` gave `expected a declaration …, found ''` at `lib.my:7:1`; now `expected ']' to close list literal, found ')'` at `lib.my:3:15`, as `myla check lib.my` (`first_error_with` #1, #2).
- **The same code**: `stage3 selfhost/gen_main.my lib` of the round-4 tool and of this one give the same assembly for x86-64, aarch64 and wasm32, and so do the 37 programs of `examples/`; bootstrap fixed point 19,596,984 bytes.
- **Check time** (callgrind, `build/myla check`, embedded library; round 4's tool, then this one): hello world without an import 39,356,608 → 38,844,918 instructions (the string and hole skips without a column count per code point pay for the keyword test per line), with `from std.io import println` 101,161,805 → 100,669,428; wall clock, minimum of 3 × 40 runs on the shared machine: 7.90 → 7.75 ms and 19.97 → 20.04 ms.
- **Suites**: `myla test` of `lexer.my` 133/133, `parser.my` 196/196, `ast.my` 62/62, `checker.my` 855/855, `loader.my` 129/129; `scripts/test.sh fast` 784 tests OK; `scripts/test.sh` 1,409 tests OK (336 skipped subtests).

## Proposals (decisions left open)

1. **The marker's form.** Built: an empty block whose range is empty at its `{` (no cost: every pass walks it as an empty block, and only `is_unread_body` tells it). Alternative: a block holding `panic("internal error: …")` from no place, which the interpreter would also refuse loudly: measured 1.7 M instructions more per check (the renamer and the checker walk it in each of ~1,500 bodies). I recommend the built form, and the same one-line guard in the interpreter's call of a function ([[MYLA-414]]'s file) if P1 wants it.
2. **A parenthesised expression is a tuple's first element.** `(f<A, B>(x))` reads as a tuple of comparisons, as the parser knows a tuple only at its comma; `return a < b, c > (d)`, a tuple without parentheses, stays one generic call, so that `return pair<A, B>(x)` keeps working. Alternative: treat `return`'s tuple as a literal too.
3. **An f-string hole's brackets close in it** (a new lex error). Alternative: only end the scan at the hole's comma, leaving `f"{g(1} {2)}"` to the checker's placeholder count. A hole with a comma of its own at the top, `f"{a, b}"`, is left to the checker's count as before.
4. **Z4's place for an attribute is lexical**: the start of a line or after `;`, `{`, `}`. A `#test` at the start of a line inside a body is still skipped in an imported module (as in round 4) and now in a body read late too, while the entry rejects it. Alternative: track function bodies' braces in the lexer (a field more and `body_ahead` at every `{` of an eagerly lexed module).
5. **An escape that ends a line inside a skipped string** sends the body back to eager lexing (its error at load) instead of deferring the identical error.

## The owner's decision (2026-11-11)

The proposals stand as built (D189).
