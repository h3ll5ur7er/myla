---
id: MYLA-182
title: "Deep input segfaults the self-hosted parser and interpreter: a stack depth guard"
type: bug
status: todo
priority: high
labels: [selfhost, parser, interpreter, lsp]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). Stack depth is unguarded everywhere but native user code:

- `build/myla check` on `let x = ((((…1000…))))` segfaults; so does the language server on the same document (an editor can produce it by paste), with no message. `python3 myla.py check` dies with a raw `RecursionError`.
- `build/myla run`, `test` and `repl` segfault at about 900 levels of plain recursion (`return 1 + f(n - 1)`), where the native binary of the same program handles 50,000: `Interp.eval` has a 2.5 KB frame, `eval_name_call` 3.7 KB, because every IR slot gets a frame cell of its own ([[MYLA-183]] is the structural fix). The Python interpreter now reports `runtime error: stack overflow` ([[MYLA-79]]).
- `std.json`'s limit was lowered to 200 for this ([[MYLA-79]]); it can go back up once the interpreters survive more.

- [ ] A depth counter in both parsers: "expression nested too deeply" as a parse error at a documented depth, in both toolchains alike (error-corpus file; the language server reports it as a diagnostic)
- [ ] The self-hosted interpreter reports `runtime error: stack overflow` instead of dying: a depth counter in `eval`/`exec_stmt`, or a guard page with a signal handler
- [ ] Native binaries report `runtime error: stack overflow` on the main stack's guard page (with [[MYLA-172]] for worker stacks)
