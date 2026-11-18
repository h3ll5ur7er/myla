---
id: MYLA-809
title: "Async code: a mutating method on a place writes a copy when the call awaits (H5)"
type: bug
status: review
priority: high
labels: [anf, async, interpreter, native, round-7]
---
Filed by [[MYLA-791]] for H5 of [[Project/Review-2026-11-17]]: old, on every runner (interpreter, x86-64, aarch64, wasm32), so no differential test saw it.

In an async function a mutating method call on a place lost its write when the call had an `await` and the receiver wasn't a name or `name[literal]`: `g[i + 1].push(await f())`, `s.rows[await f()].push(x)` and `gg[0][await f()].push(x)` changed a copy. [[selfhost/anf.my]]'s `Norm.callee` put such a receiver into a temporary (`let %aw1 = g[i + 1]`), and `Norm.expr`'s `Index` put the base of an index with an `await` into one (`let %aw1 = c.g`). 26 of the review's 36 forms (`repro-r6/native/async_place_writes.my`) left another state than their sync twin.

- [x] A place (`is_place`: a variable, its fields and elements at any depth, any index but a slice) keeps its variable and fields; only its indices are evaluated, left to right, into temporaries when something after them has an `await` (`Norm.place`: a method's receiver, an assignment's target)
- [x] An assignment whose target has an `await` evaluates its value first, as its sync twin does (`gg[c.tick(1)][await f()] = [c.tick(3)]` ran `tick(1)` first)
- [x] M11, with it: `xs[::await one()]` (`index_values`)
- [x] The test: each form against its sync twin, interpreted and natively

## Evidence

- `tests/burn/test_async_place_writes.py` (new): the review's 36 forms and 11 more (a place counted from the end, the order of the indices against the arguments and of an assignment's value, the awaited slice bounds of M11), each in an async function against the same statement in a plain one with the awaited calls plain; the program prints `same <form>` for each, and must print it all interpreted and natively (`MYLA_TEST_TARGET` for the target). At [[MYLA-791]]'s base: 31 forms `DIFFERENT` interpreted, then `index out of bounds` (`g[1][::0 - await aat(1)]`), and `async_slice_step_neg can't be lowered to the IR` at build. After: 47 of 47 `same` interpreted, on x86-64, aarch64 (qemu) and, for the review's file, wasm32 (Node); the test passes natively and with `MYLA_TEST_TARGET=aarch64-linux`.
- The review's `async_method_on_place_loses_write.my`: `2 1 1 1 2` before, `2 2 2 2 2` after, interpreted and natively.
- `selfhost/anf.my`'s cases: 21 of 21 (`is_place` 4, `index_values` 1, new).
