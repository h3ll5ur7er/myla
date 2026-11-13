---
id: MYLA-544
title: "R2 The checker: `x.format(spec)` on a builtin, a negated char literal, literals beside typed operands"
type: bug
status: review
priority: medium
labels: [checker, round-6]
---
Work package R2 of [[Project/Review-2026-11-12]]. Files: `selfhost/checker.my`. Same lane as [[MYLA-417]] and [[MYLA-394]] (reopened) and [[MYLA-538]] (raised to `high`).

- [x] **`x.format(spec)` on `T: Format` with a builtin `T`** checks, and then the interpreter fails inside itself and `myla build` says `can't be lowered`. A user type works, and so does `f"{x}"` (`repro-r5/checker/bug5_format_method_on_builtin.my`):

  ```myla
  fun show<T: Format>(x: T) -> str { return x.format("") }
  fun main() {
      print(show(5))
  }
  ```
- [x] `let v: uint8 = -'a'` is accepted and prints 159 (`bug4_neg_char_literal_unsigned.my`)
- [x] A literal left of a typed operand is typed differently from one on its right (`gap1_literal_left_of_typed_operand.my`)
- [x] The expected type isn't passed through an overloaded operator (`gap2_expected_type_through_operator.my`, [[MYLA-367]])
- [x] The hint for a static method called on a value (`low1_static_on_value_hint.my`)
- [x] `docs/Language/Lexical-structure.md`, line 107: "`128i8` is therefore accepted and wraps to -128" is false now (it is a type error, while `-128i8` works); line 106's "there are no negative literals" should say that a negated literal is checked as the value it denotes
- [x] The review's low item (§3, "Checker and parser"): a finite 65-deep type is told about "polymorphic recursion", and `myla check` accepts what `myla build` refuses (added by the round's lead)

## What changed

- **C8** (`x.format(spec)` on a builtin `T: Format`): the value's print form by the spec, as `f"{x:spec}"` gives it, with std.fmt, on every runner. Interpreted (`eval_method_call`, [[selfhost/interp.my]], the interpreter lane's file, a few lines): before the field-call fallback, a builtin value's `format` is `format_spec_value` with the spec; a spec that isn't one fails in the program's std.fmt when the program loads it (as native code does), else at the call. Natively (`builtin_format`, [[selfhost/lower.my]], the lowering lane's file): `std$fmt$fmt_int`, `fmt_float` or `fmt_text`, the spec a value, as `render_spec` does for a hole. The checker had it right already.
- **`-'a'`** (`infer_unary`): a negated char literal of an unsigned type is `integer literal -97 (the char literal negated) does not fit in 'uint8'`; in a signed type it is -97, as before.
- **Literals left of typed operands** (`literal_waits`, `left_literal`): an unsuffixed number literal on the left of `==`, `<`, `+` or another arithmetic operator takes the type of a number of its kind on its right that isn't a literal, as one on the right takes the left's: `5000000000 + big`, `-1 + big`, `-1 == big` with `big: int64`, `3000000000 > u` with `u: uint32`, `-2.5 * f` with `f: float32`; `-1 == u` with `u: uint64` is `integer literal -1 does not fit in 'uint64'` (it was a type mismatch). An integer literal that doesn't fit `int32` waits for the right side instead of failing at once. A range takes the same (`u..4294967295`, `-2..big`, `5000000000..big`), and so do the arms of an `if` or a `match`: a negated integer literal, and a float literal, take another arm's type (`if c { -1 } else { big }`, `match n { 0 => -1.5, _ => f }`).
- **The expected type through an operator** (`op_hint`, `literal_struct`): an operator trait's method gives `Self` (D53), so a struct or enum expected of an arithmetic operator is expected of its left operand: `let c: V<int64> = V { v: 2 } + V { v: 5000000000 }`. A struct literal of number literals takes the other operand's type, as a number literal does: `V { v: 2 } + V { v: 1u8 }` is a `V<uint8>`, `V { v: 250 } == x` with `x: V<uint8>`.
- **The static hint** (`bare_type`): `'tag' is a function of 'Bx<int32>' without 'self': call it on the type, 'Bx.tag(…)', not on a value`.
- **The 65-deep type** (`call_target`, the lowering's file): only an instance that is itself at the limit (type arguments 64 types deep, or more than 2,048 parts) is refused a larger one, so a deep type the program writes (`mk(x)` with `x` a list nested 65 or 100 deep) builds and runs natively, as it runs interpreted; the three polymorphic recursions of [[MYLA-415]]'s test are refused as before, at the same calls with the same messages. `myla check` accepting a polymorphic recursion that `myla build` refuses stays, by design ([[Architecture/Monomorphization]]: the interpreter runs it).
- **Docs**: [[Language/Lexical-structure]] (negated literals checked as their value, a literal typed by the other operand on either side, a range's bound, an arm), [[Language/Methods-and-traits]] (`x.format(spec)` of a primitive `T`; a generic trait's bound held with its arguments, [[MYLA-538]]), [[Language/Concurrency]] (D95 in evaluation order, [[MYLA-394]]), [[Architecture/Monomorphization]] (the limit's rule).

## Evidence

- **Tests first**, each failing at `6e699ca` (the base compiler, or the `#test` case against the base code) and passing after:
  - Parity programs, pinned, interpreted = native (`tests/burn/test_compiler_parity.py`): `format_method_on_a_builtin_type_parameter` (16 lines: every integer width's kinds, floats' precision, char, bool, str, a user type, a nested generic `Format` impl, specs computed at run time; also `--checked`, aarch64 under qemu and wasm32 under node, the same output), `literals_left_of_typed_operands` (13 lines, a type error before: `integer literal 5000000000 does not fit in 'int32'`), and `test_a_deep_type_the_program_writes_is_no_recursion` (65 and 100 deep: `true` on both runners; before, `the instances of 'mk' nest without end`; also aarch64 and wasm32 by hand).
  - `test_an_invalid_spec_of_a_builtin_format_is_a_runtime_error`: an invalid run-time spec is the program's runtime error on both runners (exit 1, the output before it kept), and `myla test` passes a case expecting its panic; before the follow-up commit the interpreter's own std.fmt panicked and ended `myla test`. The position still differs (filed as [[MYLA-565]]).
  - Error corpus, pinned: `type_negative_char_literal_unsigned.my` (was accepted), `type_literal_left_of_unsigned_operand.my` (was `type mismatch: 'int32' vs 'uint64'`).
  - `selfhost/checker.my` cases: `errors_of` ×5 (the static hint, the literals left and in a range and an arm, `-1 == u`, `-'a'`, the expected type and a struct of literals through `+`), `literal_waits` ×4, `op_hint`, `bare_type` ×2, `literal_struct`.
- **Reproducers** (`repro-r5/checker/`): `bug5_format_method_on_builtin.my` prints `P`, `V(P)`, `5`, `V(5)` interpreted and natively (an internal error on both before); `bug4` is the error above; `gap1` checks and prints `5000000005`, `4`, `5000000005`, `4`, `false`; `gap2` checks; `low1` gives the bare name.
- Generated probes (scratch): 16 literal programs (`-1 == u`, `300 + u8`, `-2.5 * f32`, `1.5 + n` still an error, `1 == g()` still typed by the left's `int32` hint, `c + 1` and `'a' + 1` still chars, `'0' + d` a `uint8`, `V { v: 2 } + 5` and `+ W { … }` still errors, ranges, arms, `-'a'` in `int8`/`int32`, `-'\0'`, a struct of literals against `V<uint8>`, `1 + s` with a string): each as the language says.
- **Suites** (for the lane's four tasks): the bootstrap's fixed point after every commit; the checker's cases (866 at round 5's end → 989, all pass), `lower.my`'s 140 and `interp.my`'s 442; `scripts/test.sh fast` 872 OK (3 skipped) before the last commit and again after it; the full `scripts/test.sh`: 1,558 tests, 341 skipped, one failure, `test_selfhost_interp`'s `range_beyond_int32` (`3000000000..3000000002` reported at its end, not its start: a literal waited for another literal), fixed by the last commit, after which `test_selfhost_interp`, `test_error_corpus`, `test_selfhost_checker` and `test_compiler_parity` pass (625 + 7 OK). `test_embedded_std` passes too: the lane changes nothing in `lib/`.
- **Check time**: see [[MYLA-538]]'s evidence: the lane's four tasks cost a hello world +0.13 % and a std.http server +0.24 % of `myla check`'s instructions (callgrind), nearly all of it this task's typing of left literals; a first version cost 0.48 % and 0.89 %, before the literal checks were made allocation-free (`literal_waits` a pattern match, `left_literal` called for literals only).
