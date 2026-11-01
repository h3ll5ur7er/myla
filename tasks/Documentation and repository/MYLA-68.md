---
id: MYLA-68
title: Agent skill that teaches coding agents Myla
type: improvement
status: done
priority: high
labels: [docs, agents]
---
Coding agents keep mistaking Myla for Rust or Swift (`fn`, semicolons, tail-expression returns, `E::A`, `xs.push(v)`, `x += 1`, `.unwrap()`, `|x|` lambdas). An [Agent Skill](https://agentskills.io) gives them a compact, correct picture of the language whenever they touch a `.my` file.

- [x] `.claude/skills/myla/SKILL.md` (Claude Code) and the same file in `.agents/skills/myla/` (Codex, Gemini CLI, Copilot, Cursor, OpenCode)
- [x] A complete example program that runs identically in the interpreter and natively and passes its `#test`
- [x] A table of Rust/Swift habits and their Myla equivalents; every "doesn't work" row checked against `myla check`
- [x] Types and conversions (incl. `float` = `float32`, literals vs variables), syntax notes, repository workflow
- [x] A pointer from `AGENTS.md`, outside the Genbeya block
- [x] Review the wording; keep the skill in step with the language (update it with each language change, like the wiki): the rule is in [[Development/Conventions]]; updated for concurrency (D89 to D97), `become`, the generated grammar, `build/myla` and the `module` directive in the review triage of 2026-10-31

## Evidence (sign-off, 2026-10-31)

The review of 31 October 2026 ([[Project/Review-2026-10]]) found one wrong rule in the skill: "nested patterns like `Some(Ok(x))` need a `_` arm". They don't: `Some(Ok(v))`, `Some(Err(e))` and `None` are exhaustive (`python3 myla.py check` accepts the program without a `_` arm, as [[Language/Structs-enums-and-match]] says). The line is corrected in both copies, and the standard-library line names `std.json`, `std.toml`, `std.num`, `std.task` and the `remove_*`/`rename`/`current_dir` functions of `std.fs` it left out. `diff -q .agents/skills/myla/SKILL.md .claude/skills/myla/SKILL.md`: identical.
