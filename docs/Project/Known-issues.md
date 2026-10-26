# Known issues

Open bugs and gaps found by the October 2026 review, by component. Each has a task with steps to reproduce; this page is the overview. When a task is done, remove its line here.

[TOC]

## Python toolchain

The reference implementation. Most problems are places where the native backend and the interpreter disagree.

| Task | Problem | Priority |
| --- | --- | --- |
| [[MYLA-9]] | Mangled names of generic instantiations can collide | low |
| [[MYLA-14]] | Exhaustiveness rejects nested and `true \| false` matches | low |
| [[MYLA-17]] | Native runtime: short writes, silent traps | low |
| [[MYLA-18]] | Strings are never freed | low |
| [[MYLA-59]] | A `match` ending an arm block must produce a value | low |
| [[MYLA-20]] | Code hygiene | low |

## Self-hosted compiler

| Task | Problem | Priority |
| --- | --- | --- |
| [[MYLA-74]] | The Myla interpreter copies containers on every update (quadratic loops) | low |
| [[MYLA-31]] | Without a stdlib root, `std` resolves to `/std` (`scripts/build.sh`) | low |
| [[MYLA-33]], [[MYLA-34]], [[MYLA-35]] | Latent issues, dead code, `justfile` recipes | low |

Also by design (from the earlier known-issues list in [[Archive/known_issues]]): x86-64 Linux is the only target (D2), and the stdlib root is passed explicitly.

## Editor tooling

| Task | Problem | Priority |
| --- | --- | --- |
| [[MYLA-53]], [[MYLA-54]], [[MYLA-55]] | VS Code settings and packaging, grammar and snippets, machine-specific workspace settings | low |

The tree-sitter grammar ([[MYLA-47]]) and the Python language server's bugs ([[MYLA-49]], [[MYLA-50]], [[MYLA-51]]) are superseded by the `Tooling in Myla` epic ([[MYLA-77]], [[MYLA-80]]).

## Documentation and repository

| Task | Problem | Priority |
| --- | --- | --- |
| [[MYLA-56]] | Docstrings point at moved or stale documents | low |
| [[MYLA-57]] | `examples/playground.my` is a scratch file pinned by the tests | low |
| [[MYLA-58]] | pytest vs unittest; the slow burn suite | low |
