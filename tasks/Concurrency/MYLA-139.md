---
id: MYLA-139
title: Concurrency in the self-hosted interpreter
type: feature
status: done
priority: medium
labels: [concurrency, interpreter, selfhost]
---
D89 (6), after [[MYLA-138]]: the synchronous tree walker stays for code that can't suspend; what lies on the path to an `await` (an async function's body, and the statements and expressions containing one, which the checker marks) runs on an async evaluator compiled stackless.

- [x] Stage 1, one task at a time: a child task runs to its end when its `async let` starts it, on copies of the variables, its failure (a runtime error or an `exit`) held for `await` or the end of its scope; actors are `VActor` handles to states only their methods change; `std.task` runs as written
- [x] The parity programs of [[MYLA-136]] (`CONCURRENCY_PROGRAMS` in `tests/burn/test_selfhost_interp.py`, and `examples/concurrency.my` in the corpus)
- [x] Stage 2, interleaving at suspension points: what can suspend is marked by the interpreter (`anf.my`: `stmt_suspends`, cached by statement), not by the checker
- [x] Stage 2: the async evaluator, delegating to the synchronous one below every statement without an `await` or `async let`, and a scheduler switching tasks at each `await`

Stage 1 ran every program whose tasks needn't make progress side by side. Stage 2 also runs those whose tasks must take turns: a child that waits for its parent to change an actor (`while await f.get() == false {}` started before the parent sets the flag).

## Stage 2: how it works

- `anf.my` normalizes an async body: each `await` in a `let` of its own (`let %aw1 = await f(x)`), what is evaluated before it in the same expression put into a temporary first; `&&`/`||` with an `await` on the right become an `if`, a `match` with one in an arm a statement assigning a temporary, a `while` whose condition has one tests it at the top of its body. New nodes take fresh ids and the types of the nodes they stand for.
- The async evaluator runs a normalized body's statements as continuations (`KStmts`, `KScope`, `KWhile`, `KFor`, `KLet`) of its call (`AFrame`) in its task. A statement without an `await` or `async let` runs on the tree walker. An awaited call is dispatched by the ordinary call code with `defer` set: entering a body that can suspend hands its frame (parameters, `self`) to the async evaluator instead of running it.
- The tasks take turns: round robin, switching after each `await`'s value is there, and when a task waits for a child or for a scope's children. A `return`, `break`, `continue` or failure leaves the blocks one continuation at a time, so a scope still waits for its children.
- A match guard can't `await` (a checker error in both checkers), so arms are chosen at once.

## Found on the way

- A `?` in an `async let`'s initializer made the Python interpreter's parent return from its `await` with the child's value; it is a checker error now in both checkers ("'?' can't stand in an 'async let'…", `examples/errors/type_try_in_async_let.my`).

## Evidence (stage 1)

- `CONCURRENCY_PROGRAMS` (13 programs: awaited calls and values, an async method, `async let` results, scopes waiting for children, copies, an awaited and an unawaited child failing, `exit` in a child, an actor counter, copies in and out of an actor, reentrancy and two actors calling each other, `task.all`) and `examples/concurrency.my` print, fail and exit as in the Python CLI; before, the self-hosted interpreter refused every one of them.
- Unit 621, integration 2, burn 790 (5 skipped) and the extension's 54 tests pass; the bootstrap reaches its byte-identical fixed point (5,407,346 bytes).
