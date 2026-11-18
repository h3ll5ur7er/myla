---
id: MYLA-759
title: "Agent harness: skills"
type: feature
status: review
priority: medium
labels: [examples, agent]
---

A skill is a directory with a `SKILL.md` whose frontmatter has a `name` and a `description` (the format of `.agents/skills/`). The harness finds them in the workspace's `.agents/skills/` and `.claude/skills/` and in the configured directories, lists their names and descriptions in the system prompt, and gives the model a `load_skill` tool that reads a skill's `SKILL.md` or one of its files, a page at a time.

- [x] Parse a `SKILL.md`'s frontmatter (`name`, `description`, quoted or not); a skill without them is skipped
- [x] Discovery, the first skill of a name wins (workspace before user)
- [x] The system prompt's list, and the instruction to load a skill before a task it covers
- [x] `load_skill(name, file?, start?)`: never outside the skill's directory

Against Qwen3.6-35B on 2026-11-17 the model loaded the `myla` skill, then its `reference/syntax.md` in two pages, before it answered. It once left `name` out of a `load_skill` call and recovered from the error.
