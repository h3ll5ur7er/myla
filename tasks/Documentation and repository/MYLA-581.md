---
id: MYLA-581
title: The myla skill read against the code, with reference files
type: chore
status: review
priority: medium
labels: [docs, agents]
---
The `myla` agent skill (`.claude/skills/myla/`, mirrored in `.agents/skills/myla/`) was written from the wiki and grew row by row. Before the next language features, read the actual code of the compiler (`selfhost/`) and the standard library (`lib/std/`) and bring the skill in step with it, as the lookup for agents and the owner.

Done means: every claim in `SKILL.md` checked against the code (and, where unsure, with `build/myla check`/`run`), wrong or stale ones corrected, and reference files beside it for what is too long for the core page. Both copies identical; every `myla` block in them checks.

- [x] Front end read (lexer, tokens, parser, AST, grammar): `reference/syntax.md`
- [x] Checker and loader read (types, traits, generics, modules, implicit modules, builtins): `reference/builtins.md`
- [x] Interpreter, CLI, project tool, test runner, REPL read: `reference/toolchain.md`
- [x] Back end read (lowering, IR, passes, backends, runtimes, bootstrap): `reference/compiler.md`, with where a new feature is wired in
- [x] Standard library read: `reference/stdlib.md`, one entry per module
- [x] `SKILL.md` corrected and pointing to the reference files
- [x] Every `myla` block in the skill checked; both copies identical

## Evidence

- Read by area: the front end (`tokens`, `lexer`, `parser`, `ast`, `grammar/myla.ebnf`), the checker and loader, the interpreter and every tool entry point with `scripts/` and CI, the back end (lowering, IR, passes, backends, runtimes, bootstrap; five features traced through their commits: ae328a7 `defer`, f7294b1/a1a4729 `+=`, a7dcd66 `if` values, 284c878 `if let`, 00ccfb0 slices), and all 59 modules of `lib/std/` (each module's count of `pub` items matched against the index). Claims were checked with probe programs under `build/myla check`/`run`/`build`.
- `SKILL.md`: about 30 claims corrected (among them: a `match` statement whose arms all return counts as a return; `#main` is optional on `async fun main()`; `import std.task` binds only the full path; `m.contains` is the compiler's; `impl<K, V> [K: V]` needs `K: Eq + Hash`; `--only` matches function names, not labels; the seed is needed for any change to `selfhost/` or `lib/std/`; `task.workers` is async; `num.parse_int` is an `Option<int64>`; `text.ints` a `Result`; `int_in` leaves `hi` out) and the facts agents trip on added (`let x = 1⏎ - 2` silently leaves 1; `xs.pop()` is a `T`; lambdas always take parentheses; struct fields need commas; an integer literal never becomes a float; nothing but scalars and `Format` types prints; the interpreter's 2,500-call depth; `IoError` isn't `Eq`; staging a seed before using a new builtin or primitive; soft keywords).
- `reference/`: `syntax.md`, `builtins.md`, `stdlib.md`, `toolchain.md`, `compiler.md` (with the checklist for adding a language feature).
- `test_doc_blocks.py` now also runs the skill's blocks and requires the two copies to be identical: before the reference files, `test_the_skill_has_blocks` failed (2 blocks); after, 5/5 pass (12 skill blocks checked, run and built natively with the same output). A changed byte in the mirror fails `SkillCopies` and names the file. Writing the core page's example, its `// output:` was first wrong (18 for 12); the test caught it.
- What the read found stale or doubtful elsewhere is [[MYLA-582]].
