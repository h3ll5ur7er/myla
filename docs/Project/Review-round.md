# Review round

The tasks waiting in `review` for the owner's sign-off, triaged on 2026-10-31 so that a manual review can go through them one by one. Each was checked against the code of that day, not against its own text: the code, tests or error-corpus files it names exist, its tests pass, and the bugs it fixed were run again and behave. Remove this page, or start a new one, once the round is done.

[TOC]

## Before you start

- **Rebuild `build/myla` first:** `scripts/bootstrap.sh`. The binary is ignored by git, so a checkout keeps whatever was built last; one from before the fixes makes newer tasks look broken (it doesn't know `__unlink`, and accepts what [[MYLA-111]] rejects).
- Many tasks name functions of `selfhost/codegen.my` that have since moved into the IR lowering (`selfhost/lower.my`, D79, [[MYLA-107]]), and test classes or flags that [[MYLA-107]] removed on purpose (`--ir`, `--ir-stats`). Their behaviour is still pinned by the tests named; only the prose is old.
- 29 of them, mostly older ones, have their evidence inside the checklist or their How section rather than under `## Evidence`; that was the convention then.
- To sign a task off, set its `status` to `done`; to send one back, to `todo` or `in-progress` with a line saying what is missing.

## What the triage changed

- **Closed as superseded:** [[MYLA-48]] and [[MYLA-52]], about the Python language server, which [[MYLA-80]] replaced and [[MYLA-83]] removed; their cases run against the Myla server now.
- **Fixed on the way:** the `myla` skill (it called actors and `async` "not Myla"; now it has concurrency, `become`, the generated grammar, `build/myla` and the `module` directive, [[MYLA-68]], [[MYLA-70]]); the comment in `.vscode/settings.json` ([[MYLA-55]]); two stale comments about the removed IR fallback ([[MYLA-107]]); the CLI's docstring ([[MYLA-82]]); [[MYLA-101]]'s evidence; [[MYLA-67]]'s tick for [[MYLA-109]]; nine links to deleted files ([[MYLA-1]]).
- **Leftovers split into tasks of their own**, so the original can be signed off: [[MYLA-151]] (map tombstones, from [[MYLA-16]]), [[MYLA-152]] (a closure named like a builtin, from [[MYLA-102]], a real bug), [[MYLA-153]] (the burn suite's speed, from [[MYLA-58]]), [[MYLA-154]] (a generated TextMate grammar, from [[MYLA-77]]), [[MYLA-155]] (the language server's open points, from [[MYLA-97]]), [[MYLA-157]] (a leak to confirm, from [[MYLA-4]]).
- **New, found while checking:** [[MYLA-156]] (CI runs no gdb, so the debugger tests are always skipped there; actions to move off Node 20).

## Verdicts

All 87 tasks below are ready for sign-off. Where the note column says more, it is something to know while reviewing, not something missing.

## Python toolchain (28)

| Task | Title | Priority | Note |
| --- | --- | --- | --- |
| [[MYLA-2]] | Native code keeps a dangling pointer when a match binding's list grows | high | Evidence inside the checklist (older format). |
| [[MYLA-3]] | Compiler crashes assigning a heap-owning struct to a field | high | Evidence inside the checklist. |
| [[MYLA-4]] | Python backend crashes the self-hosted checker on an unknown parameter type | high | The literal leak it notes is now [[MYLA-157]]. |
| [[MYLA-5]] | Native int64 division of the minimum by -1 dies with SIGFPE | medium | - |
| [[MYLA-6]] | Float-to-integer casts crash the interpreter or disagree with native code | medium | - |
| [[MYLA-7]] | Literal patterns outside the scrutinee's range match differently natively | medium | - |
| [[MYLA-8]] | Native code evaluates operands and arguments right to left | medium | - |
| [[MYLA-9]] | Generic instantiations can get the same mangled name | low | - |
| [[MYLA-10]] | Errors from imported modules are shown against the entry file | medium | Its Python language-server items are history ([[MYLA-83]], D71); the fix holds in all three CLIs. |
| [[MYLA-11]] | #test attributes in imported modules can't name module-level declarations | medium | - |
| [[MYLA-12]] | Interpreter crashes on strings that aren't valid UTF-8 | medium | - |
| [[MYLA-13]] | #derive(Eq) rejects char and float fields | low | - |
| [[MYLA-14]] | Exhaustiveness check rejects exhaustive matches | low | - |
| [[MYLA-15]] | `>=` right after generic type arguments is a parse error | low | - |
| [[MYLA-16]] | Native allocator scans one free list linearly | high | Its optional map tombstones moved to [[MYLA-151]]. |
| [[MYLA-17]] | Native runtime robustness: partial writes and malformed UTF-8 | low | - |
| [[MYLA-18]] | Strings from +, format and builders are never freed | low | - |
| [[MYLA-20]] | Code hygiene in the Python toolchain | low | The `myla lsp` guard item is moot since [[MYLA-83]]. |
| [[MYLA-59]] | A match ending a match-arm block must produce a value | low | - |
| [[MYLA-60]] | Code generator spends almost all of stage 1 collecting list types | high | - |
| [[MYLA-71]] | Emit DWARF line tables so gdb can step through Myla source | medium | - |
| [[MYLA-72]] | `?` in a lambda is checked against the enclosing function's return type | medium | Cosmetic: an empty `Done when` heading. |
| [[MYLA-75]] | Partial application evaluates its filled arguments at every call | medium | - |
| [[MYLA-76]] | Optional semicolons as statement separators | medium | - |
| [[MYLA-84]] | The lexers disagree on non-ASCII letters in identifiers | low | Review with [[MYLA-86]] (both D72). |
| [[MYLA-85]] | A builtin that copies a byte range of a string | low | - |
| [[MYLA-86]] | More escapes in string literals (\r, \0, \u{…}) | low | Review with [[MYLA-84]]. |
| [[MYLA-111]] | #test arguments and expected values are not type-checked | low | Check it with a fresh `build/myla` (the fix is newer than an old build). |

## Self-hosted compiler (20)

| Task | Title | Priority | Note |
| --- | --- | --- | --- |
| [[MYLA-21]] | Destructuring a tuple of boxed recursive enums is miscompiled | high | Names `gen_destruct`, now in the IR lowering (`selfhost/lower.my`). |
| [[MYLA-22]] | Self-hosted runtime never frees memory | high | Evidence inline. |
| [[MYLA-23]] | #derive(Eq) on recursive enums compares box addresses | medium | - |
| [[MYLA-24]] | format() with a char or float argument segfaults | medium | Names functions moved into `lower.my`. |
| [[MYLA-25]] | remove() on a map changes copies of the map too | medium | Names functions moved into `lower.my`. |
| [[MYLA-26]] | Partial application of a function returning an aggregate returns garbage | medium | Names functions moved into `lower.my`. |
| [[MYLA-27]] | Const folding treats references to other consts as 0 | medium | - |
| [[MYLA-28]] | Self-hosted diagnostics: shifted positions and no messages | low | - |
| [[MYLA-29]] | Self-hosted compiler has no float support | medium | - |
| [[MYLA-30]] | Self-hosted loader concatenates modules as text | medium | - |
| [[MYLA-31]] | Missing stdlib root makes std imports resolve to /std | low | - |
| [[MYLA-32]] | Self-hosted interpreter diverges from the Python interpreter | medium | Review with [[MYLA-74]]. |
| [[MYLA-33]] | Latent issues in the self-hosted compiler | low | Names functions moved into `lower.my`. |
| [[MYLA-34]] | Remove dead code and bring-up probes from selfhost | low | - |
| [[MYLA-35]] | justfile recipes drop arguments and leave files behind | low | Its How says `rm -f`; the code uses `remove_file` ([[MYLA-96]]). |
| [[MYLA-73]] | Self-hosted lexer wraps integer literals of 2^63 and above | low | - |
| [[MYLA-74]] | Self-hosted interpreter copies containers on every update | low | Review with [[MYLA-32]]. |
| [[MYLA-87]] | Derived Eq on an enum without payloads compares tags | medium | - |
| [[MYLA-102]] | A local closure shadows a top-level function of the same name | high | Fixed for functions; a closure named like a builtin is [[MYLA-152]]. |
| [[MYLA-119]] | Lookup tables instead of linear searches in the self-hosted compiler | medium | Self-compile measured at about 1.03 s (claimed 0.97 s). |

## IR (6)

| Task | Title | Priority | Note |
| --- | --- | --- | --- |
| [[MYLA-103]] | IR: data types, flags and scalar functions | high | Its evidence names `--ir`, `--ir-stats` and test classes that [[MYLA-107]] removed on purpose. |
| [[MYLA-104]] | IR: aggregates | high | Evidence names a test class [[MYLA-107]] removed. |
| [[MYLA-105]] | IR: heap values, ownership and the verifier | high | Bootstrap numbers in MYLA-105 to 108 are from their time. |
| [[MYLA-106]] | IR: closures, function values and the rest | medium | Evidence names the removed `--ir` classes. |
| [[MYLA-107]] | IR: the default, and the old path removed | medium | Its two stale comments (gen_main.my, IR.md) are fixed. |
| [[MYLA-108]] | IR: optimisations | medium | Its two items not kept went to MYLA-121/122 (done). |

## Roadmap ideas (4)

| Task | Title | Priority | Note |
| --- | --- | --- | --- |
| [[MYLA-64]] | Project tool like cargo | medium | Epic: sub-tasks MYLA-88 to 98 are in this round; `myla fmt` deferred by design. |
| [[MYLA-65]] | Better error messages | medium | Epic: sub-tasks MYLA-10/17/28 in this round. |
| [[MYLA-66]] | Debugger support | low | Epic: the interpreter debugger is [[MYLA-116]] (backlog), the DAP front end [[MYLA-99]]. |
| [[MYLA-67]] | A mid-level IR between the checker and the code generators | high | Epic; the MYLA-109 tick fixed. LLVM continues as [[MYLA-62]]. |

## Editor tooling (6)

| Task | Title | Priority | Note |
| --- | --- | --- | --- |
| [[MYLA-53]] | VS Code extension settings and packaging | low | Its How still mentions `myla.pythonPath` (removed, text only). |
| [[MYLA-54]] | VS Code grammar and snippets describe a different Myla | low | - |
| [[MYLA-55]] | Workspace settings point at another machine | low | The `.vscode/settings.json` comment is rewritten (no `.venv`, no `pythonPath`). |
| [[MYLA-99]] | Debug adapter in the VS Code extension | medium | Its self-hosted debugger test is skipped in CI (no gdb): [[MYLA-156]]. |
| [[MYLA-100]] | VS Code extension overhaul | medium | Evidence says 51 extension tests; there are 54. |
| [[MYLA-101]] | Build the VS Code extension's .vsix in CI | medium | Evidence updated with the green CI run. |

## Tooling in Myla (7)

| Task | Title | Priority | Note |
| --- | --- | --- | --- |
| [[MYLA-77]] | Grammar description and a tree-sitter grammar generated from it | medium | Its optional TextMate item is [[MYLA-154]]. |
| [[MYLA-78]] | Read from stdin in the standard library | medium | - |
| [[MYLA-79]] | JSON in the standard library | medium | - |
| [[MYLA-80]] | Language server written in Myla | medium | Its comparison with the Python server is history. |
| [[MYLA-81]] | `myla test` parity in the self-hosted CLI | medium | Its "left as is" limits (symlinked roots, uint64 above 2^63) are untracked by choice. |
| [[MYLA-82]] | REPL written in Myla | low | `src/myla/cli.py`'s docstring is fixed. |
| [[MYLA-83]] | Retire the Python tools that have Myla replacements | low | Its last trace (`pythonPath` in `.vscode/settings.json`) is gone. |

## Project tool (9)

| Task | Title | Priority | Note |
| --- | --- | --- | --- |
| [[MYLA-88]] | Directory functions in std.fs | medium | - |
| [[MYLA-89]] | std.toml - the TOML subset of D73 | medium | - |
| [[MYLA-92]] | Packages in both loaders (--package name=dir) | medium | - |
| [[MYLA-93]] | Project model - manifest, lock file and path dependencies | medium | - |
| [[MYLA-94]] | Project commands in build/myla (path dependencies) | medium | Its How says `clean` runs `rm -rf`; now `remove_dir_all`. |
| [[MYLA-95]] | Git dependencies and myla fetch | medium | - |
| [[MYLA-96]] | Remove and rename files and directories in std.fs | low | Its intro paragraph is from before the task. |
| [[MYLA-97]] | Language server - list files with list_dir and resolve into packages | low | Its open points are [[MYLA-155]]. |
| [[MYLA-98]] | std.fs.current_dir and the __getcwd primitive | medium | - |

## Documentation and repository (5)

| Task | Title | Priority | Note |
| --- | --- | --- | --- |
| [[MYLA-56]] | Docs inside code point at moved or stale pages | low | - |
| [[MYLA-57]] | playground.my is a scratch file pinned by the test gates | low | - |
| [[MYLA-58]] | Test tooling: pytest vs unittest, and a slow burn suite | low | Done as specified; the suite grew back: [[MYLA-153]]. |
| [[MYLA-68]] | Agent skill that teaches coding agents Myla | high | The skill is updated (concurrency, `become`, grammar, `build/myla`, `module`): read it. |
| [[MYLA-69]] | Continuous integration with GitHub Actions | high | "burn ≈ 25 s" is now about 4 min ([[MYLA-153]]). |

## Rust edition (1)

| Task | Title | Priority | Note |
| --- | --- | --- | --- |
| [[MYLA-70]] | Remove the Rust edition from the repository | low | The skill's misleading line about actors and `async` is fixed. |

## Project (1)

| Task | Title | Priority | Note |
| --- | --- | --- | --- |
| [[MYLA-1]] | Introduce Genbeya tasks and wiki | medium | Left for you: "Review the wiki and the task priorities". The link check is done. |
