# Known issues

Open bugs and gaps found by the October 2026 review, by component. Each has a task with steps to reproduce; this page is the overview. When a task is done, remove its line here.

[TOC]

## Python toolchain

The reference implementation. Most problems are places where the native backend and the interpreter disagree.

| Task | Problem | Priority |
| --- | --- | --- |
| [[MYLA-2]] | A `match` binding holding a list dangles when the arm grows the original (use-after-free) | high |
| [[MYLA-3]] | `o.inner = Inner{…}` with heap fields crashes the compiler (`NotImplementedError`) | high |
| [[MYLA-10]] | Errors in imported modules are shown against the entry file | medium |
| [[MYLA-5]] | `int64` minimum `/ -1` and `% -1` crash natively | medium |
| [[MYLA-6]] | Float → integer casts of NaN/inf crash the interpreter; out-of-range casts disagree | medium |
| [[MYLA-7]] | Out-of-range literal patterns (`-1` on `uint8`) match differently | medium |
| [[MYLA-8]] | Native evaluation order is right to left | medium |
| [[MYLA-11]] | `#test` in an imported module can't name that module's declarations | medium |
| [[MYLA-12]] | The interpreter crashes on strings that aren't valid UTF-8 | medium |
| [[MYLA-9]] | Mangled names of generic instantiations can collide | low |
| [[MYLA-13]] | `#derive(Eq)` rejects `char` and float fields | low |
| [[MYLA-14]] | Exhaustiveness rejects nested and `true \| false` matches | low |
| [[MYLA-15]] | `Option<int>= x` is a parse error | low |
| [[MYLA-17]] | Native runtime: short writes, malformed UTF-8 in `chars`, silent traps | low |
| [[MYLA-18]] | Strings are never freed | low |
| [[MYLA-59]] | A `match` ending an arm block must produce a value | low |
| [[MYLA-19]], [[MYLA-20]] | No REPL; code hygiene | low |

## Self-hosted compiler

| Task | Problem | Priority |
| --- | --- | --- |
| [[MYLA-21]] | Destructuring boxed recursive enums is miscompiled; breaks the self-hosted `myla run` on method calls | high |
| [[MYLA-22]] | `__free` returns immediately: memory is never reused, and reference-counting bugs are hidden | high |
| [[MYLA-29]] | No floats (the AST drops the literal's digits) | medium |
| [[MYLA-30]] | The loader concatenates modules: name collisions, no packages or module aliases | medium |
| [[MYLA-23]] | `#derive(Eq)` on recursive enums compares addresses | medium |
| [[MYLA-24]] | `format` with a `char` segfaults | medium |
| [[MYLA-25]] | `remove` on a map changes its copies | medium |
| [[MYLA-26]] | Partial application of an aggregate-returning function returns garbage | medium |
| [[MYLA-27]] | Const folding treats const references as 0 | medium |
| [[MYLA-32]] | The Myla interpreter diverges from the Python one in nine ways | medium |
| [[MYLA-28]] | Diagnostics have shifted positions and no messages | low |
| [[MYLA-31]] | Without a stdlib root, `std` resolves to `/std` (`scripts/build.sh`) | low |
| [[MYLA-33]], [[MYLA-34]], [[MYLA-35]] | Latent issues, dead code, `justfile` recipes | low |

Also by design (from the earlier known-issues list in [[Archive/known_issues]]): x86-64 Linux is the only target (D2), and the stdlib root is passed explicitly.

## Rust edition

| Task | Problem | Priority |
| --- | --- | --- |
| [[MYLA-36]] | The native backend silently miscompiles tail expressions, `if` values, hex literals, `&&`/`||`, unsigned and 32-bit arithmetic | high |
| [[MYLA-37]] | Native backend crashes and coverage | medium |
| [[MYLA-38]], [[MYLA-39]], [[MYLA-41]] | Interpreter: names ignored in struct/enum handling; control flow leaking out of functions; numeric kinds and hashing | medium |
| [[MYLA-40]] | Channels never close; actors deadlock on self-calls | medium |
| [[MYLA-42]] | No static checking at all | medium |
| [[MYLA-45]] | Tests check too little | medium |
| [[MYLA-43]], [[MYLA-44]], [[MYLA-46]], [[MYLA-47]] | Language gaps, unused dependencies, docs vs parser, tree-sitter grammar | low |
| [[MYLA-70]] | The Rust edition is to be removed once nothing depends on it | low |

## Editor tooling

| Task | Problem | Priority |
| --- | --- | --- |
| [[MYLA-48]] | Short declaration names are found inside the keyword | medium |
| [[MYLA-52]] | No language-server tests | medium |
| [[MYLA-49]], [[MYLA-50]], [[MYLA-51]] | Lifecycle races, dead code, name-only resolution | low |
| [[MYLA-53]], [[MYLA-54]], [[MYLA-55]] | VS Code settings and packaging, grammar and snippets, machine-specific workspace settings | low |

## Documentation and repository

| Task | Problem | Priority |
| --- | --- | --- |
| [[MYLA-56]] | Docstrings point at moved or stale documents | low |
| [[MYLA-57]] | `examples/playground.my` is a scratch file pinned by the tests | low |
| [[MYLA-58]] | pytest vs unittest; the slow burn suite | low |
