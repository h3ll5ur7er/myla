---
id: MYLA-182
title: "Deep input segfaults the self-hosted parser and interpreter: a stack depth guard"
type: bug
status: done
priority: high
labels: [selfhost, parser, interpreter, lsp]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). Stack depth is unguarded everywhere but native user code:

- `build/myla check` on `let x = ((((…1000…))))` segfaults; so does the language server on the same document (an editor can produce it by paste), with no message. `python3 myla.py check` dies with a raw `RecursionError`.
- `build/myla run`, `test` and `repl` segfault at about 900 levels of plain recursion (`return 1 + f(n - 1)`), where the native binary of the same program handles 50,000: `Interp.eval` has a 2.5 KB frame, `eval_name_call` 3.7 KB, because every IR slot gets a frame cell of its own ([[MYLA-183]] is the structural fix). The Python interpreter now reports `runtime error: stack overflow` ([[MYLA-79]]).
- `std.json`'s limit was lowered to 200 for this ([[MYLA-79]]); it can go back up once the interpreters survive more.

- [x] A depth counter in both parsers: "expression nested too deeply" as a parse error at a documented depth, in both toolchains alike (error-corpus file; the language server reports it as a diagnostic)
- [x] The self-hosted interpreter reports `runtime error: stack overflow` instead of dying: a depth counter in `eval`/`exec_stmt`, or a guard page with a signal handler
- [x] Native binaries report `runtime error: stack overflow` on the main stack's guard page (with [[MYLA-172]] for worker stacks)

## Evidence

- Parsers: one counter in both, raised on entering an expression, a unary operand, a type, a block or a pattern; past 256 (`MAX_NESTING`) `expression (type, block, pattern) nested too deeply` at the current token. Seven deeply nested inputs give the same errors, positions and trees from both (parser gate: four new `SYNTAX_ERRORS`; corpus `parse_nested_too_deeply.my`); `python3 myla.py check` no longer dies with a `RecursionError` (`parse` raises Python's recursion limit to 100,000).
- Self-hosted interpreter: past 2,500 calls (`MAX_CALL_DEPTH`) `runtime error: stack overflow`, exit 1, instead of a segfault at about 900; heavy recursive functions take some 25 KB per call. Both backends' `_start` raise the main stack's soft limit to 120 MiB (`prlimit64`), which makes room for it: `down(5000)` ran in the interpreter after it, `down(2600)` is now the error.
- Native binaries (both backends): a SIGSEGV handler on a 64 KiB alternate stack, installed by `_start`, reports a fault next to the stack pointer as `runtime error: stack overflow`, exit 1 (`test_a_stack_overflow_is_reported`: `down(1000000)` runs, `down(100000000)` gives the error, from both backends; the interpreters print the same). Any other fault still kills the program with SIGSEGV and no message (checked with a null dereference put into a compiled program). Workers' stacks: [[MYLA-172]].
- Unit 622, integration 2, burn 826 (5 skipped) and the extension's 54 tests pass on commit 12f6e94; the bootstrap reaches its byte-identical fixed point (6,153,392 bytes).
- CI (the first run with the tree-sitter CLI) failed `test_syntax_errors_give_error_nodes`: `parse_nested_too_deeply.my` breaks a limit of the parsers, not a rule of the grammar, so tree-sitter parses it; the test now leaves such files out (`_PARSER_LIMITS`). Locally the module's 10 tests pass with the CLI installed (the verification worktree has none, so they skipped there).
