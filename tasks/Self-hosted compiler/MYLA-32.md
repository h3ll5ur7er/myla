---
id: MYLA-32
title: Self-hosted interpreter diverges from the Python interpreter
type: bug
status: review
priority: medium
labels: [selfhost, interpreter, parity]
---
[[selfhost/interp.my]] differs from `src/myla/interpreter.py` in several ways:

- [x] Float literals evaluate to `0.0` (fixed by [[MYLA-29]])
- [x] `panic` and `assert` exit 1 without printing the message
- [x] Integer division by zero returns 0 instead of a runtime error
- [x] A missing map key yields `VUnit` instead of a runtime error
- [x] `>>` on `uint64` is an arithmetic shift
- [x] The receiver is evaluated after the arguments, and a `var self` receiver is evaluated twice
- [x] `for i in a..b` materializes the whole range, truncated to `int32`
- [ ] Lists, maps and scopes are copied on every update, so assignment is O(n): recorded as [[MYLA-74]]
- [x] `Value.to_string` formats a `float64`, which the self-hosted codegen can't render: every float path of the stage3-built `myla run` crashes (fixed by [[MYLA-29]])

## Done when

- [x] Each item fixed or recorded as a known difference on [[Project/Known-issues]]
- [x] `test_selfhost_interp.py` covers the fixed items

## How

- **Runtime errors** are recorded with the Python interpreter's message and the expression they happen at (`Interp.rt_err`, set by `fail`), and stop the program like `exit`. `interp_main` and the CLI print them as the Python CLI does, in the file of the expression (loader spans, [[MYLA-28]]): list and string indexes out of bounds (read and write), missing map keys (with Python's `repr` of the key), division and modulo by zero, `pop` on an empty list, `panic`, `assert` (with or without a message), `unreachable`, and a program without an entry point.
- **Places**: assignments, `push`/`pop`, `remove`, `append`/`append_byte` and `var self` calls resolve their target once (`place_of`: the variable and a field/index path, each index evaluated once, containing indexes read first) and write it back through it, instead of re-evaluating the target. The value of an assignment and of a `push` is evaluated before the container is read, so `push(xs, pop(xs))` keeps the pop, and nothing is written once a `?`, `return` or error is pending.
- **Order**: a method's receiver is evaluated before its arguments.
- `>>` on `uint64` is a logical shift; `for i in a..b` counts with an `int64` without building a list; a `?` in a lambda with an expression body returns from the lambda.

## Found on the way

- `==` and `!=` on strings **concatenated** them (`"ab" == "ab"` printed `abab`, `if s == ""` was never taken): the concatenation test ran before the comparisons for every operator.
- Partial application of a method read the method as a field ([[MYLA-26]]).

## Tests

`tests/burn/test_selfhost_interp.py`: `test_runtime_behaviour_matches_the_python_cli` compares stdout, stderr and the exit code with the Python CLI on the four runtime error files of the corpus, 20 programs for the items above (`INTERP_PROGRAMS`) and a runtime error inside an imported module; `test_parity_programs_match_the_oracle` runs the codegen gate's parity programs through the interpreter. On the previous code 28 of these cases fail; now all pass, and the stage-3-built `myla run` prints byte for byte what the Python CLI prints (stdout, stderr, exit code) on all 165 examples and error files.
