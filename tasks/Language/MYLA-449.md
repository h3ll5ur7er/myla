---
id: MYLA-449
title: "A literal before the element that fixes a wider type must fit int32"
type: improvement
status: done
priority: low
labels: [language, types, checker]
---
Found by the checker lane of round 5 ([[MYLA-417]]). Since L2, the literals of a list's or map's column take the type a later element fixes, each checked again against it. But each is first checked against the type the column has so far, `int32` for a first literal, so one that doesn't fit `int32` fails before the later element is seen:

```myla error
fun main() {
    let big: int64 = 5000000000
    let a = [4000000000, big]          // integer literal 4000000000 does not fit in 'int32'
    let m = [1: 4000000000, 2: big]    // the same
}
```

`[big, 4000000000]` and `let a: [int64] = [4000000000, big]` check.

- [x] A literal that doesn't fit the column's type while only literals are in it waits for a later element's type, and the error comes at the end of the column if none fixes a type it fits (`column_step`, `close_column` in `selfhost/checker.my`)
- [x] Error-corpus files for the error that remains, a parity program for the lists and maps that now check

## What changed

`column_step` and `close_column` in [[selfhost/checker.my]], `LitColumn.waiting`. Without a type expected of the elements, a literal (`adapts`) that fails against the type the column's literals have so far (an `int32` for a first one) no longer fails at once: it joins the column's literals and waits. The next element that fixes a type (one that isn't such a literal) gives it to all of them, each checked again, the one that waited too: `[4000000000, big]` with `big: int64` is an `[int64]`, `[18000000000000000000, 2, u]` with `u: uint64` a `[uint64]`, `[1, -3000000000, 4000000000, big]` an `[int64]`; map keys and values alike. If none comes, `close_column` checks the literals again against the type the others have and reports the first that fails, where it stands: `[4000000000, 1]` and `[1: 4000000000, 2: 7]` say `integer literal 4000000000 does not fit in 'int32'` as before; `[4000000000, 3u8]` now says it doesn't fit in `uint8`, the type the column ends with. With an expected element type the literal is checked against it as before (`let a: [int32] = [4000000000, big]` is the error at the literal). A literal in a nested list that is checked before the element that would widen it still fails (`[[4000000000], [big]]`), as `[[1, 2], [3u8]]` is a mismatch: a column's literals wait, an earlier list of them doesn't.

## Evidence

- **Tests first**, each failing before (the base checker, `bccc624`) and passing after:
  - `selfhost/checker.my` `errors_of` ×10: before, `#79`–`#82` (`[4000000000, big]`, `[1, 4000000000, -3000000000, big]`, the map's values and keys, `[18000000000000000000, 2, u]`) said `does not fit in 'int32'`, `#83` (`[4000000000, 3u8]`) `'int32'` where it is `'uint8'`; `[4000000000, 1]`, `[4000000000]`, `[4000000000, 1, n]`, the annotated `[int32]` and `[4000000000, 2.5]` keep their error.
  - Parity program `literals_wait_for_the_element_that_fixes_a_wider_type` (pinned, interpreted = native; also `--checked`): before, `integer literal 4000000000 does not fit in 'int32'`.
  - Error corpus (pinned `.stderr`): `type_literal_wider_than_the_type_a_later_element_fixes` (`[4000000000, 3u8]`: before `'int32'`, after `'uint8'`, at the literal) and `type_literal_no_later_element_fixes_a_wider_type` (`[1: 4000000000, 2: 7]`, the error that remains, at the literal).
- **Check time**: see [[MYLA-448]] (one measurement for both): a hello world +0.001 %.
- **Suites** (both items, one commit): `scripts/bootstrap.sh` reaches its fixed point; `scripts/test.sh fast` 851 tests OK (3 skipped); `tests.burn.test_error_corpus` 342 OK; the full `scripts/test.sh` 1,522 tests, 338 skipped, one failure: `test_selfhost_codegen`'s `test_children_run_in_parallel` (cpu 1.12 s for 1.13 s of wall time, a timing test of the runtime's workers), which fails run alone too while the machine's load is 7 to 9 on its 4 CPUs (six lanes); this change is the checker's only.

## Review 2026-11-12

Signed off in [[Project/Review-2026-11-12]].
