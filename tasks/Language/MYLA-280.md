---
id: MYLA-280
title: "Slices and indexes from the end: `xs[a:b:step]`, `xs[-1]` or `xs[^1]`"
type: feature
status: done
priority: medium
labels: [language, collections, design]
---
The owner's wish (2026-11-05): Python's slicing and indexing of lists. Today `xs[i]` reads one element (a list's, a byte of a `str`, a map's value) and there is no slicing (a part of a string is built with `StringBuilder.append(s, start, end)`).

```myla
let xs = [10, 20, 30, 40, 50]
print(xs[1:3])     // [20, 30]
print(xs[:2])      // [10, 20]
print(xs[::2])     // [10, 30, 50]
print(xs[::-1])    // [50, 40, 30, 20, 10]
```

## What it costs

- **Slices** (`xs[a:b]`, `xs[a:]`, `xs[:b]`, `xs[a:b:step]`): a new expression in the parser, the checker (on lists and strings, integer bounds) and the interpreter; natively one routine in `std.rt`, written in Myla, so every backend gets it at once. A slice is a new list (values are values, D48): it costs its length, as Python's does. About as large as let-else (D137): one to two days with tests, docs and the grammar.
- **Indexes from the end**: in each backend's bounds check (x86-64, aarch64, wasm32) and the interpreter; small, but it touches every index.

## Questions for the owner

| Question | Options | Recommendation |
| --- | --- | --- |
| Indexes from the end | A: Python's negative indexes (`xs[-1]`); B: C#'s `^` (`xs[^1]` is the last, `xs[1:^1]` drops both ends) | **B**: the same convenience, but `xs[i - 1]` with `i == 0` stays an error instead of reading the last element without a word (Python's best-known trap), and an ordinary index costs no extra test. With A, every index pays one comparison more |
| Slice bounds out of range | clamped (Python: `xs[2:99]` is the rest) or an error | **clamped**, as in Python: a slice never fails; a single index still does |
| Strings | slices by bytes, an error off a character's boundary (Rust); or by characters (O(n)) | **by bytes, an error off a boundary**: `s[i]` is a byte today, and `len(s)` counts bytes |
| Assigning to a slice (`xs[1:3] = ys`) | yes, or not yet | **not yet**: reading is the common use |
| Maps | no slices | no |

Then:
- [x] The decision for indexes from the end and the step (D142)
- [x] The other three questions (D143): bounds clamped, `str` sliced by bytes with an error off a character's boundary, no assignment to a slice yet
- [x] Parser and grammar (`[a:b:step]` inside an index, kept apart from a map literal), checker, interpreter, `std.rt`'s slice routine, the bounds checks for `^`
- [x] [[Language/Collections-and-strings]], [[Language/Expressions-and-operators]]
- [x] Tests: parity programs on every target, the error corpus

## Decided (2026-11-05): D142

- **From the end:** `^`, in an index and in a slice's bounds: `xs[^1]`, `xs[1:^1]`, `xs[^3:]`. A plain negative index stays an error.
- **The step:** an ordinary signed integer, as in Python: `xs[::2]`, `xs[::-1]`, `xs[^1:0:-2]`; with a negative step the bounds default to the end and the start.

```myla
let xs = [10, 20, 30, 40, 50]
print(xs[^1])       // 50
print(xs[1:^1])     // [20, 30, 40]
print(xs[^2:])      // [40, 50]
print(xs[::-1])     // [50, 40, 30, 20, 10]
print(xs[::2])      // [10, 30, 50]
```

## Decided (2026-11-05): D143

The owner chose the recommendations of the three other rows: bounds clamped (`xs[2:99]` is the rest, `xs[5:2]` empty), a `str` sliced by bytes with a runtime error off a character's boundary, no assignment to a slice yet.

## Built (2026-11-05)

- **Syntax:** the parser writes `xs[^n]` as `Index(xs, Unary("^", n))` and a slice as `Index(xs, Binary(":", start, stop))` (with the step, `Binary(":", that, step)`), a bound left out a `Hole`: every walker over expressions already goes into them, so captures, renaming, `await` and the analyses need nothing new. `^` anywhere else is a parse error.
- **Checker:** a slice is the same kind of list or string, its bounds and step integers (the step without `^`); a map has none; `xs[^1] = v` assigns, a slice can't be assigned to.
- **std.slice** (new, Myla): `range_of` gives the indices (the bounds clamped, a negative step backwards); `take<T>`, `take_str` and `str_whole` are what native code calls. The interpreter takes its indices from `range_of` too.
- **Lowering:** `^n` is the cell's length less `n`, then the usual bounds check; a slice calls `take` (an instance per element type) or `str_whole` and `take_str`, with two new runtime errors checked where the slice stands, `slice step is zero` and `a slice bound inside a character`, on every target.
- [[tests/burn/test_slices.py]]: every form against the interpreter and native code, the same program on aarch64 and wasm32 (`PROGRAMS["slices"]`), the runtime errors in each runner at the slice's position, the type errors; `#test` cases in `std.slice`; the grammar's `index_part` and tree-sitter.
