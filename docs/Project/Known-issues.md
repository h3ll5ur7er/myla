# Known issues

Open bugs and gaps found by the October 2026 review, by component. Each has a task with steps to reproduce; this page is the overview. When a task is done, remove its line here.

[TOC]

## Python toolchain

The reference implementation. Most problems are places where the native backend and the interpreter disagree.

No open issues.

## Self-hosted compiler

No open issues.

Also by design (from the earlier known-issues list in [[Archive/known_issues]]): x86-64 Linux is the only target (D2). The stdlib root no longer has to be passed: `build/myla` finds it from its own location ([[MYLA-31]]).

## Editor tooling

No open issues. The tree-sitter grammar ([[MYLA-47]]) and the Python language server's bugs ([[MYLA-49]], [[MYLA-50]], [[MYLA-51]]) are superseded by the `Tooling in Myla` epic ([[MYLA-77]], [[MYLA-80]]).

## Documentation and repository

No open issues.
