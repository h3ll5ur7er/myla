---
id: MYLA-68
title: Agent skill that teaches coding agents Myla
type: improvement
status: review
priority: high
labels: [docs, agents]
---
Coding agents keep mistaking Myla for Rust or Swift (`fn`, semicolons, tail-expression returns, `E::A`, `xs.push(v)`, `x += 1`, `.unwrap()`, `|x|` lambdas). An [Agent Skill](https://agentskills.io) gives them a compact, correct picture of the language whenever they touch a `.my` file.

- [x] `.claude/skills/myla/SKILL.md` (Claude Code) and the same file in `.agents/skills/myla/` (Codex, Gemini CLI, Copilot, Cursor, OpenCode)
- [x] A complete example program that runs identically in the interpreter and natively and passes its `#test`
- [x] A table of Rust/Swift habits and their Myla equivalents; every "doesn't work" row checked against `myla check`
- [x] Types and conversions (incl. `float` = `float32`, literals vs variables), syntax notes, repository workflow
- [x] A pointer from `AGENTS.md`, outside the Genbeya block
- [ ] Review the wording; keep the skill in step with the language (update it with each language change, like the wiki)
