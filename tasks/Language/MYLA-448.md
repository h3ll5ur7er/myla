---
id: MYLA-448
title: "A compound assignment's hoisted map key loses the map's key type"
type: bug
status: done
priority: low
labels: [language, types, parser, checker]
---
Found by the checker lane of round 5 ([[MYLA-417]]). `m[k] += v` computes an index that isn't a name or a literal once, in a hidden `let %index… = k` before the assignment (the parser's `hoisted`, [[MYLA-223]]). That `let` has no type, so a key that needs the map's key type to be inferred fails, though `m[k] = m[k] + v` checks:

```myla error
fun main() {
    var r: [Result<str, int>: int] = [:]
    r[Ok("a")] = 1
    r[Ok("a")] += 10      // cannot infer type parameter(s) E
    var m: [Option<int>: int] = [:]
    m[None] = 0
    m[None] += 1          // cannot infer type argument(s) for 'None'
}
```

- [x] The hoisted key takes the map's key type (the checker could check `%index` lets against the place they index, or the parser could hoist only what can't be typed alone)
- [x] A parity program with both lines, interpreted and natively

## Found again in integration (2026-11-10)

The same hidden temporary blocks a compound assignment to a field whose value is a generic call: `acc.items += lst()` (with `fun lst<T>() -> [T]`) still says `cannot infer type parameter(s) T for 'lst'`, while `acc.items = lst()` now checks ([[Project/Review-2026-11-09]]'s `gap_expected_through_try.my`, line 54).

## What changed

- **The hidden `let`** (`check_compound`, `index_key_hint`, `hoists_an_index` in [[selfhost/checker.my]]): the checker recognizes the parser's `if true { let %index… = k; place = place op v }` and checks each hidden `let` against the key type of the place it indexes (the map's key type, `int32` for a list, found with `check_lvalue` on the container, whose own hidden names are already declared), as the plain assignment's place gives its index. The parser is unchanged: typing in the checker covers what the parser can't know (`m[pick()] += 1` with a generic `pick`, `w[2 * 2500000000] += 1` with `int64` keys), which hoisting only "what can't be typed alone" wouldn't.
- **The right side** (`infer_binary`): a compound assignment's value is already the plain form's `Binary(op, place, v)`, so it gets the same expected types. Two gaps both forms shared: `s + e` with `s: str` gives `e` no hint (`s += blank()` with `fun blank<T: Blank>() -> T` couldn't infer `T`), now `str`; and an arithmetic operator whose left side is no number or char (a list, a bool, a tuple) checked the right side first, so `acc.items += lst()` and `acc.items = acc.items + lst()` both said `cannot infer type parameter(s) T for 'lst'` and `[1] + 2` said `type mismatch: '[int32]' vs 'int32' (no implicit conversion between numeric types)`. The operator is the error now: `operator '+' requires numeric or string operands`, `operator '-' requires integer operands`. Lists have no `+`, so `acc.items += lst()` stays an error ([[Project/Review-2026-11-09]]'s `gap_expected_through_try.my`, line 54, now reports the missing operator).

## Evidence

- **Tests first**, each failing before (checked against the base checker, `bccc624`) and passing after:
  - `selfhost/checker.my` `errors_of` ×12: before, `#67`–`#70` `cannot infer type argument(s) for 'K.A'`, `cannot infer the element type of an empty list`, `integer literal 2500000000 does not fit in 'int32'`, `map key must be 'uint8', found 'int32'`; `#74`/`#75` `cannot infer type parameter(s) T for 'lst'` (compound and plain); `#76`/`#77` `type mismatch: '[int32]' vs 'int32'`, `'bool' vs 'int32'`; `#78` `cannot infer type parameter(s) T for 'blank'`. Plus `is_hidden_index` ×2, `names_index` ×3. The checker's cases: 921 → 948 with [[MYLA-449]]'s, all pass.
  - Parity program `compound_assignments_type_as_their_plain_form` (`tests/burn/test_compiler_parity.py`, pinned, interpreted = native; also `--checked`): maps keyed by `Result`, `Option`, `int64` and `uint8` with hoisted keys, a field's map, `acc.grid[i + 1][^(i + 1)] += 5000000000`, `+=`, `*=`, `<<=`, `-=`, `%=`, `str += blank()`. Before: `cannot infer type parameter(s) E` at `r[Ok("a")] += 10`. Its plain twin (each `x op= e` written `x = x op e`) prints the same.
  - Error corpus `type_compound_assign_without_the_operator` (pinned `.stderr`): before, `cannot infer type parameter(s) T for 'lst'` at 16:21; after, `operator '+' requires numeric or string operands` at the `+=`, as the plain form at its `+`.
- **Every form against its plain form** (a scratch script, not kept): 22 places (names, fields, list indexes `0`, `i`, `i + 1`, `ix()`, `^1`, `^(i + 1)`, `Option`/`Result`/`int64`/generic map keys, nested) × the ten operators × 10 right sides (`1`, `blank()`, `lst()`, `2.5`, `"x"`, `big`, `5000000000`, `None`, `-1`, `'a'`), each `x op= e` checked beside `x = x op e`, comparing exit status and messages: before 498 of 2,200 pairs differed, after none.
- **Check time** (callgrind, `build/myla check`, instructions, both items): `examples/hello.my` 41,206,892 → 41,207,329 (+0.001 %); with `std.io` 60,363,444 → 60,365,055 (+0.003 %).
- **Suites** (both items, one commit): `scripts/bootstrap.sh` reaches its fixed point; `scripts/test.sh fast` 851 tests OK (3 skipped); `tests.burn.test_error_corpus` 342 OK; the full `scripts/test.sh` 1,522 tests, 338 skipped, one failure: `test_selfhost_codegen`'s `test_children_run_in_parallel` (cpu 1.12 s for 1.13 s of wall time, a timing test of the runtime's workers), which fails run alone too while the machine's load is 7 to 9 on its 4 CPUs (six lanes); this change is the checker's only.

## Review 2026-11-12

Signed off in [[Project/Review-2026-11-12]].
