# Known issues

Open bugs and gaps found by the October 2026 review, by component. Each has a task with steps to reproduce; this page is the overview. When a task is done, remove its line here.

[TOC]

## Python toolchain

The reference implementation. Most problems are places where the native backend and the interpreter disagree.

| Task | Problem | Priority |
| --- | --- | --- |
| [[MYLA-14]] | Exhaustiveness rejects nested and `true \| false` matches | low |
| [[MYLA-17]] | Native runtime: short writes, silent traps | low |
| [[MYLA-18]] | Strings are never freed | low |

## Self-hosted compiler

| Task | Problem | Priority |
| --- | --- | --- |
| [[MYLA-74]] | The Myla interpreter copies containers on every update (quadratic loops) | low |

Also by design (from the earlier known-issues list in [[Archive/known_issues]]): x86-64 Linux is the only target (D2), and the stdlib root is passed explicitly.

## Editor tooling

No open issues. The tree-sitter grammar ([[MYLA-47]]) and the Python language server's bugs ([[MYLA-49]], [[MYLA-50]], [[MYLA-51]]) are superseded by the `Tooling in Myla` epic ([[MYLA-77]], [[MYLA-80]]).

## Documentation and repository

| Task | Problem | Priority |
| --- | --- | --- |
| [[MYLA-58]] | pytest vs unittest; the slow burn suite | low |
