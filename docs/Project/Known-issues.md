# Known issues

Open bugs and gaps found by the October 2026 review, by component. Each has a task with steps to reproduce; this page is the overview. When a task is done, remove its line here.

[TOC]

## Python toolchain

The reference implementation. Most problems are places where the native backend and the interpreter disagree.

- To confirm: a `?` failing inside a list or map literal may leak the half-built literal in the Python backend ([[MYLA-157]]).

(The lexers' disagreement on non-ASCII identifiers is settled: both take Unicode's XID, D72, [[MYLA-84]].)

## Self-hosted compiler

- A local closure named like a builtin (`let build = (n: int) => n + 1`, then `build(41)`) calls the builtin in the self-hosted interpreter and native code: nothing printed, a segfault, or a compile error ([[MYLA-152]]).

Also by design (from the earlier known-issues list in [[Archive/known_issues]]): x86-64 Linux is the only target (D2). The stdlib root no longer has to be passed: `build/myla` finds it from its own location ([[MYLA-31]]).

## Editor tooling

No open issues. The tree-sitter grammar ([[MYLA-47]]) and the Python language server's bugs ([[MYLA-49]], [[MYLA-50]], [[MYLA-51]]) are superseded by the `Tooling in Myla` epic ([[MYLA-77]], [[MYLA-80]]).

## Documentation and repository

No open issues.
