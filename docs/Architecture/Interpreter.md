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
| actor handle | `ActorRef(state, lock)`: `_copy` leaves it alone, so a copy reaches the same actor (D89) |
| an `async let`'s name | `_Task(thread, value, error)` |

**Value semantics by copying.** `_copy` deep-copies aggregates whenever a value is bound, assigned, passed, returned, stored or captured. There is no copy-on-write here; the observable behaviour matches the native backend's reference counting.

## Execution

- Environments are chains of dictionaries (`_Env`); each call starts a fresh frame whose parent is nothing, since functions see only their parameters, constants and other functions.
- `return`, `break` and `continue` are Python exceptions; `std.process.exit` raises `_ExitSignal`, caught by `run()`, which returns the exit status.
- `become` (D87) raises `_BecomeSignal` with the callee's body and its new frame; `_run`, the loop every call goes through, catches it and goes on with them, so a chain of `become`s doesn't nest Python calls. The self-hosted interpreter does the same with `Ctrl.CBecome` and `run_tail`; a `var self` method that `become` calls on `self` passes `self` on, and the caller stores back the last one's.
- Constants are evaluated once from the checker's folded values.
- `var self` methods bind `self` to the caller's actual object (`_resolve_struct` finds it), so field writes reach the caller; read-only `self` gets a copy.
- Operators on structs and enums inside a bounded generic body are dispatched at run time to `Type.add`, `Type.eq`, `Type.cmp`, … (`_dispatch_operator`); everywhere else they were desugared into method calls.
- Runtime errors raise `MylaRuntimeError` with the node's position.

## Concurrency

D89, [[MYLA-136]], [[Language/Concurrency]].

- **Async functions** are ordinary functions: `await f()` runs `f` in the task that awaits it. Only `async let` starts another task.
- **`async let`** (`_start_task`) runs its initializer on a Python thread, in a frame holding copies of the variables it mentions (`_names_in`). `await name` joins the thread and gives a copy of the result, or raises the child's error. The scope that started a child waits for it when it ends, normally or not (`_close_scope`, from `_exec_block`, a `for` body and a match arm's block); a child that failed unawaited fails the scope, unless the scope is failing already.
- **Actors.** A struct literal of an actor makes an `ActorRef`. A method of the actor is called on the handle: from outside it takes the actor's lock in the calling thread and gives a copy of the result (`_on_actor`); from the actor's own methods, which hold it, it is an ordinary call. The arguments were copied as for every call. `self` in its methods is the handle, so field reads and writes go to the state (`_resolve_struct`), and `self` passed on is the handle. A child task of one of its methods that reads through `self` takes the lock for the read (`_actor_field`).
- **Reentrancy, and no deadlocks.** Wherever a task waits (calling into an actor, joining a child), it first lets go of the actor it holds and takes it back afterwards (`_released`). The actor's other calls run meanwhile, and since no thread waits while holding an actor, two actors calling each other can't deadlock. The calling thread runs an actor's method. That is the same as a mailbox served one message at a time, since only one thread holds the lock.
- **Output.** `print` and `__write` write each piece under one lock, so lines of tasks running at once stay whole.
- A test with `sys.setswitchinterval(1e-6)` checks the lock: without it, increments from three tasks get lost (`tests/unit/test_concurrency.py`).

## I/O primitives

`__write` writes to the given stream, `__read` reads with `os.read` (fd 0 from the `stdin=` byte stream when one was passed, as the tests do) after flushing stdout and stderr, so a program's answer is out before it waits for the next request ([[MYLA-78]]), `__read_file` reads bytes and decodes them with `surrogateescape` (so any byte sequence survives), `__write_file`, the directory primitives `__list_dir` (`os.listdir`, each name followed by a NUL byte), `__mkdir` and `__stat` (`st_mode` or -1), whose path ends at its first NUL byte as natively ([[MYLA-88]]), `__args` (the argv passed to `Interpreter(..., argv=…)`), and `__run`, which uses `subprocess.run` with `executable=program` (no `PATH` search) and stores stderr, exit code, signal and errno for the `__run_*` primitives.

## Strings

A Myla `str` is bytes, kept as a Python `str` in which every byte that isn't part of valid UTF-8 is a lone surrogate U+DC80..U+DCFF (Python's `surrogateescape`). `_str_bytes` and `_bytes_str` convert; `len`, indexing, `append`, `__write` and `__read_file` go through them. `+` and `format` decode their result again when a sequence may have been split between the pieces (`_normalize`), so equal bytes are always equal strings and map keys. `chars` uses `_decode_chars`, the same decoder as the native `__str_chars`. The CLI sets `errors="surrogateescape"` on stdout and stderr, so the escapes go out as the original bytes ([[MYLA-12]]).

## The test runner

`run_tests()` goes through every function's `#test` attributes, evaluates arguments and the expected value, calls the function and compares with Python `==` (structural for every value type). A runtime error fails that case only.

## Known problems

- `s[i]` and `len(s)` encode the whole string each time, so byte loops over long strings are quadratic.
