---
id: MYLA-628
title: "The other library panics that are the caller's mistake point at the caller"
type: improvement
status: backlog
priority: low
labels: [std, diagnostics]
---
Follows [[MYLA-435]], which built `#track_caller` ([[Language/Attributes-and-testing#track_caller]]) and gave it to std.option's `expect`s and std.args' checks. Other functions of the standard library end in a `panic` that is their caller's mistake, and still point into their own file:

- std.list ([[lib/std/list.my]]): `xs.insert(i, x)` and `xs.remove_at(i)` with an index out of bounds (`insert: index 5 out of bounds for a list of 2`), `xs.chunks(n)` and `xs.windows(n)` with `n < 1`. They are `var self` methods of a built-in type, whose receiver is passed by address (D144): check that the hidden argument comes after it on every target.
- std.test ([[lib/std/test.my]]): `test.expect`, `expect_eq`, `expect_ne`, `fail`; under `myla test` the report shows no position, but a program run with `myla run` that uses them (a check in a script) would point at its own line.
- Any other `panic` in `lib/std/` whose message names an argument of the call (grep `panic(f"` there).

Reproducer (2026-11-13, after [[MYLA-435]]):

```myla fragment
fun main() {
    var xs = [1, 2]
    xs.insert(5, 3)
}
```

`myla run` reports `  --> <myla>/std/list.my:42:34`, not the call's `(` in `main`.

[[tests/burn/test_std_cache.py]]'s `PANIC` program fails inside `xs.chunks(0)` to have a runtime error inside a library body read late: if `chunks` takes `#track_caller`, give that test another failure inside a body (an index out of range in a std function keeps its own position).

- [ ] Mark the functions whose panic is the caller's mistake `#track_caller`, with an error-corpus file for one of each module, interpreted and natively
