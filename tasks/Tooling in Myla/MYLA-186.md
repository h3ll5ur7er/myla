---
id: MYLA-186
title: The __ primitives are callable from user code
type: bug
status: review
priority: medium
labels: [checker, stdlib]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). `fun main() { print(__getcwd()); __exit(3) }` runs under both CLIs (and exits 3). The 22 `__` primitives (`__write`, `__exit`, `__read`, `__run`, `__getcwd`, `__unlink`, `__task_cancelled`, …) are meant for `std/` (D29, D64); `_BUILTIN_FUNCS` in [[src/myla/types.py]] and the self-hosted checker only forbid *redeclaring* them.

- [x] Both checkers reject a call of a `__` name outside the standard library root (`type error: '__getcwd' is a primitive of the standard library`), with an error-corpus file
- [x] `get(m, k)`, "a prelude function, not a builtin", named on [[Language/Standard-library]] as the one exception a user can see

## Note (2026-11-01)

The rejection needs a decision: the self-hosted interpreter ([[selfhost/interp.my]]) calls the primitives directly to implement them for the programs it runs, and it isn't under the standard library root, so "only from the stdlib" would reject the toolchain itself. Either a std module of raw wrappers for it, or an exemption. The documentation item is done: [[Language/Standard-library]] names `get` and lists every primitive, saying the checkers still accept them.

## Evidence

- The owner's decision: not a rejection but a warning (D100), in both checkers, at the call's name, once per place, with a help line; silent inside the standard library (functions named `std$…`). The task's first item now reads as done in that form.
- Checker gate: `warn_primitive_called` (a call in `main`, one in a lambda) gives the same warnings from both checkers.
- In the repository only `selfhost/interp.my` calls primitives from outside the standard library (17 places: it implements them for the programs it runs); `python3 myla.py check selfhost/main.my` shows those 17 warnings, the compiler, the language server and the other tools none.
