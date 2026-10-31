---
id: MYLA-79
title: JSON in the standard library
type: feature
status: done
priority: medium
labels: [stdlib]
---
Part of the "everything in Myla" direction ([[Project/Roadmap]]); the language server's protocol is JSON-RPC ([[MYLA-80]]).

- [x] `std.json`: a `Json` enum (null, bool, number, string, array, object), a parser with positioned errors, and a serializer (string escapes, `\u` and surrogate pairs)
- [x] Written in Myla, tested with `#test` and against Python's `json` on a corpus

## How

Decision D66 on [[Project/Decisions]]; the API is on [[Language/Standard-library]].

- `std.num` (new): the self-hosted compiler's exact float-literal conversion moved here from `selfhost/floatlit.my` (deleted; the compiler, its interpreter and `floatlit_main.my` import it from `std.num`, and the interpreter's copies of `f64_from_bits`/`pow2` are gone), plus `parse_int`, `parse_float` and `format_float`, the shortest decimal that reads back, as Python's `repr` writes it. `format_float` computes the exact decimal expansion with big integers and binary-searches the number of digits (round-tripping is monotonic in it).
- `std.json` (new): `enum Json { Null, Bool, Int, Float, Str, Array, Object([(str, Json)]) }`, `parse` with `JsonError { msg, line, col }`, `to_string`, `field`. The parser follows Python's scanner: the same number grammar (an incomplete fraction or exponent is left over, so `1.` is "Extra data"), the same messages and positions (3.13's, including "Illegal trailing comma"), `NaN`/`Infinity`. It differs in rejecting lone surrogates and nesting deeper than 500. The writer matches `json.dumps(ensure_ascii=False, separators=(",", ":"))`. Parser and writer are structs with `var self` methods, as Myla has no references.
- Both modules carry `#test` cases (50 and 37).

## Evidence

- `tests/burn/test_json.py`: on 3,000 random texts (1,500 values, compact and indented ASCII), both native builds print exactly Python's re-serialization; on 3,000 broken texts (2,942 kept, 1,957 of them errors of ten kinds), the same verdicts with the same message, line and column; 5,000 floats (half random bit patterns) come out as Python's `repr`; the nesting limit; a small corpus through both interpreters; the modules' `#test` cases. About 11 s.
- The tests have teeth: counting UTF-8 continuation bytes as columns makes 516 of the broken texts differ, and switching to scientific notation at 1e15 instead of 1e16 fails the float tests.
- Speed: the first version took 64 s for this file; the binary search (8.3 s → 3.3 s for the floats) and ordinary floats in the interpreter corpus (45 s → 6 s) brought it to 11 s.
- The self-hosted float gate (`test_selfhost_floatlit.py`) passes with the moved code.
- Full run: 487 unit, 4 integration and 416 burn tests pass; the bootstrap reaches its fixed point at 7,723,409 bytes (7,611,063 before: the compiler now links all of `std.num`, `format_float` included, since Myla compiles whole modules).

## Evidence (sign-off, 2026-10-31)

The review ([[Project/Review-2026-10]]) found the nesting limit of 500 true only for compiled programs: 500 nested arrays made the self-hosted interpreter segfault (its stack is gone at about 300 levels) and the Python interpreter die with a raw `RecursionError` (at 50 levels: Python's default limit of 1,000 frames is a few dozen Myla calls deep). Two changes:

- `MAX_DEPTH` is 200, with the reason in [[src/myla/std/json.my]] and on [[Language/Standard-library]]; `test_nesting_limit` in `tests/burn/test_json.py` now parses 200 levels and rejects 201 (`err 1 201 Too deeply nested`). It can go back up with [[MYLA-182]].
- The Python interpreter raises Python's recursion limit to 100,000 when it runs a program or its tests (`_deep_stack` in [[src/myla/interpreter.py]]; pure-Python recursion lives on the heap since 3.12) and reports a program that still exhausts it as `runtime error: stack overflow` instead of a traceback. 200 nested arrays parse in both interpreters; a recursion 5,000 deep runs, also inside a task's thread; unbounded recursion prints the runtime error and exits 1.

The unit suite (621 tests), `test_json.py`, the CLI parity test and the codegen gate pass.
