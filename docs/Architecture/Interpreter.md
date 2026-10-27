# Interpreter

[[src/myla/interpreter.py]] is a tree-walking evaluator over the checked, desugared AST. It defines the language's behaviour: the native backend must print the same thing for every program.

[TOC]

## Values

| Myla | Python |
| --- | --- |
| integers, `char` | `int`, wrapped to the width after every operation (`_wrap`) |
| floats | `float`; `float32` results are rounded through `struct.pack("f")` |
| `bool`, `str` | `bool`, `str` |
| struct, tuple, enum | `StructValue(name, fields)`, `TupleValue(elems)`, `EnumValue(enum, variant, payload)` |
| list, map, builder | `ListValue`, `MapValue` (a dict: insertion order), `StringBuilderValue` (a `bytearray`) |
| function value | `ClosureValue(params, body, env, is_block)`; a `fun` used as a value has an empty env |

**Value semantics by copying.** `_copy` deep-copies aggregates whenever a value is bound, assigned, passed, returned, stored or captured. There is no copy-on-write here; the observable behaviour matches the native backend's reference counting.

## Execution

- Environments are chains of dictionaries (`_Env`); each call starts a fresh frame whose parent is nothing, since functions see only their parameters, constants and other functions.
- `return`, `break` and `continue` are Python exceptions; `std.process.exit` raises `_ExitSignal`, caught by `run()`, which returns the exit status.
- Constants are evaluated once from the checker's folded values.
- `var self` methods bind `self` to the caller's actual object (`_resolve_struct` finds it), so field writes reach the caller; read-only `self` gets a copy.
- Operators on structs and enums inside a bounded generic body are dispatched at run time to `Type.add`, `Type.eq`, `Type.cmp`, … (`_dispatch_operator`); everywhere else they were desugared into method calls.
- Runtime errors raise `MylaRuntimeError` with the node's position.

## I/O primitives

`__write` writes to the given stream, `__read` reads with `os.read` (fd 0 from the `stdin=` byte stream when one was passed, as the tests do) after flushing stdout and stderr, so a program's answer is out before it waits for the next request ([[MYLA-78]]), `__read_file` reads bytes and decodes them with `surrogateescape` (so any byte sequence survives), `__write_file`, `__args` (the argv passed to `Interpreter(..., argv=…)`), and `__run`, which uses `subprocess.run` with `executable=program` (no `PATH` search) and stores stderr, exit code, signal and errno for the `__run_*` primitives.

## Strings

A Myla `str` is bytes, kept as a Python `str` in which every byte that isn't part of valid UTF-8 is a lone surrogate U+DC80..U+DCFF (Python's `surrogateescape`). `_str_bytes` and `_bytes_str` convert; `len`, indexing, `append`, `__write` and `__read_file` go through them. `+` and `format` decode their result again when a sequence may have been split between the pieces (`_normalize`), so equal bytes are always equal strings and map keys. `chars` uses `_decode_chars`, the same decoder as the native `__str_chars`. The CLI sets `errors="surrogateescape"` on stdout and stderr, so the escapes go out as the original bytes ([[MYLA-12]]).

## The test runner

`run_tests()` goes through every function's `#test` attributes, evaluates arguments and the expected value, calls the function and compares with Python `==` (structural for every value type). A runtime error fails that case only.

## Known problems

- `s[i]` and `len(s)` encode the whole string each time, so byte loops over long strings are quadratic.
