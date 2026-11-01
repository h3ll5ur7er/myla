# Interpreter

[[selfhost/interp.my]] is a tree-walking evaluator over the checked declarations. It runs `myla run`, `myla test` and the REPL. It and the native backend must print the same thing for every program. The type information it needs at run time (integer widths, how to print and format a value, casts) comes from the checker's `resolved` table, keyed by node id.

Until the Python toolchain was retired (D101, [[MYLA-219]]), the Python interpreter (`src/myla/interpreter.py`) defined the language's behaviour and the self-hosted one mirrored it; the burn tests still compare with its output, recorded ([[Development/Testing]]).

[TOC]

## Values

| Myla | `Value` |
| --- | --- |
| integers | `VInt(int64)`, wrapped to the type's width after every operation |
| `char` | `VChar(int64)`, the code point |
| floats | `VFloat(float64)`; `float32` results are rounded to single precision |
| `bool`, `str` | `VBool`, `VStr` (a host `str`: bytes) |
| no value | `VUnit` |
| struct, tuple, enum | `VStruct(name, field names, values)`, `VTuple(elements)`, `VEnum(enum, variant, payload)` |
| list, map, builder | `VList(elements)`, `VMap(keys, values)` (parallel lists, insertion order), `VSB(bytes)` |
| function value | `VClosure(params, body, capture names, captured values, function name, is a function)`; `VCompose(functions)` for `f >> g`, `VPartial(callable, argument slots, holes)` for `f(a, _)` |
| actor handle | `VActor(i)`: its state in `Interp.actors`, so a copy reaches the same actor (D89) |
| an `async let`'s name | `VTask(i)`: the child in `Interp.tasks` |

**Value semantics.** Structs, tuples, enums, lists and maps are copied when they are bound, assigned, passed, returned and constructed; containers are updated in place ([[MYLA-74]]), so a loop of a million `push`es is linear.

## Execution

- A call starts a fresh frame (`RtFrame`: names and values), since functions see only their parameters, constants and other functions.
- Myla has no exceptions, so running a block or call returns how it finished; a pending signal on the interpreter (`Ctrl`: `return`, `break`, `continue`, `exit`, `become`) lets a `return` or `?` inside a match arm's value, or an `exit` or `panic` in the middle of an expression, leave from where it is.
- `become` (D87) leaves the call pending (`TailCall`) for the loop that runs the function (`run_tail`), which goes on with it, so a chain of `become`s doesn't nest calls; a `var self` method that `become` calls on `self` passes `self` on, and the caller stores back the last one's.
- Constants are evaluated once from the checker's folded values.
- `var self` methods write through to the caller's object; read-only `self` gets a copy.
- Operators on structs and enums are dispatched to the trait's method of the receiver's type (`Type.add`, `Type.eq`, `Type.cmp`, …); `?`, composition and partial application are evaluated directly, from what the checker recorded.
- Runtime errors carry the node's position; the CLI prints them as it prints compile errors, with the source line and carets ([[MYLA-32]]).

## Concurrency

D89, [[MYLA-139]], [[Language/Concurrency]].

- **Async functions** are ordinary calls, unless their body has an `await` or an `async let`: such a body is normalized (`anf.my`: each `await` in a `let` of its own, the order of evaluation kept) and runs on an async evaluator, its statements continuations of its call in its task. Everything else runs on the tree walker.
- **Tasks** take turns at each `await`, one at a time, first in, first out: the order the native runtime keeps on one worker (which is why `test_unit_programs.py` runs native code on one worker). An `async let` starts a child task; the scope that started it joins it when it ends. A failure in any task ends the program (D97).
- **Actors** are handles to states in `Interp.actors`. Since one task runs at a time, they need no lock.

The Python interpreter ran each `async let` child on a Python thread and gave each actor a lock instead.

## I/O primitives

The interpreter is a native program, so the primitives of the standard library (`__write`, `__read`, `__poll`, `__read_file`, `__write_file`, `__list_dir`, `__mkdir`, `__stat`, `__unlink`, `__rmdir`, `__rename`, `__getcwd`, `__run` and the `__run_*` results) call the native runtime's own and behave as in a compiled program ([[Architecture/Native-backend]]). `__args` gives the file followed by the arguments after it on the command line, as `args()` does for a binary.

## Strings

A Myla `str` is bytes, and so is the host's `str` that holds it: `len`, indexing, `+`, `format`, `==` and map keys work on the bytes, and `chars` decodes UTF-8, giving U+FFFD for each byte outside a well-formed sequence, as natively ([[MYLA-12]]).

## The test runner

`run_tests` goes through every function's and method's `#test` attributes (D116), evaluates the arguments and the expected value, calls the function and compares the values structurally. A runtime error fails that case only. A failing case shows the values as `py_repr` writes them, the Python interpreter's repr, so the report is the one the Python CLI printed ([[MYLA-81]]).

## Depth

The interpreter counts its calls: past 2,500 (`MAX_CALL_DEPTH`) it reports `runtime error: stack overflow` ([[MYLA-182]]). An interpreted call takes some 12 to 25 KB of its native stack, because every IR slot has a cell of its own ([[MYLA-183]] would share them), and the native runtime lets the main stack grow to 120 MiB ([[Architecture/Native-backend]]); a program recursing deeper than 2,500 runs natively, but not in `build/myla run`. (The Python interpreter allowed 100,000 frames.)
