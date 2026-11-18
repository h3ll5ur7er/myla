---
id: MYLA-800
title: "R7-11 Docs, skill and CI: the skill's false claims, Known issues and README after Windows, the generated tests' full size"
type: bug
status: todo
priority: medium
labels: [documentation, ci, round-7]
---
Work package of [[Project/Review-2026-11-17]], lane "Docs, skill, CI" (section 5). Files: `docs/`, `.agents/skills/`, `.claude/skills/` (kept identical), `README.md`, `AGENTS.md`, `.github/workflows/`. The reproducers are in the review's bundle (`repro-r6/`, with a README per area); each fix turns its reproducer into a test that fails before it. The owner's decision it builds: D262. New tasks it files take ids 869–876.

- [ ] The skill says `t.0.1` doesn't lex and `IoError` isn't `Eq` (both false now), omits `x86_64-windows` and `#track_caller`'s row ([[MYLA-581]]'s follow-up); `AGENTS.md` names two seeds
- [ ] README, Roadmap and Known issues still plan Windows and the website; Known issues gives 63 percent coverage (61 now); [[MYLA-715]] belongs on Known issues until fixed; about 95 links in old tasks point at the removed Python toolchain
- [ ] [[MYLA-629]]'s follow-up: README and the skill still describe D156; `cancel-in-progress` can drop a master commit's artifacts
- [ ] Decision 8: the generated tests' full size: a master-only or scheduled step with `MYLA_GENERATED=full` and a seed from the run number ([[MYLA-554]]/[[MYLA-555]]'s follow-up)
- [ ] `lldb` in CI; the burn job at 22 of its 30 minutes
- [ ] Runs last: other lanes change what the docs say
