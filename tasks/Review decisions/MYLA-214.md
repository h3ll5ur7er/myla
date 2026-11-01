---
id: MYLA-214
title: "Decision: board and process rules (done, task types, epics, pull requests)"
type: chore
status: todo
priority: low
labels: [decision, process, genbeya]
---
From the October 2026 review ([[Project/Review-2026-10]], §13.8). The rules the board follows are partly unwritten. Implementation task: [[MYLA-194]].

## Sub-questions, options and recommendations

- **What `done` means.** Options: whoever finishes a task marks it `done`; or agents move tasks to `review` and only the owner moves them to `done`. *Recommended:* the second, as practised since October, written into [[Development/Conventions]]; Known-issues entries stay until `done`.
- **Task types.** `.genbeya.yml` has no `types:`, so only `bug`, `feature`, `improvement` and `chore` are valid, and [[MYLA-144]] (`test`), [[MYLA-160]] and [[MYLA-166]] (`design`) are invalid. Options: recode them; or add `types:` with the extra ones. *Recommended:* add `types: [bug, feature, improvement, chore, decision]`, recode `design` as `decision` and `test` as `chore`, and give these decision tasks the `decision` type.
- **Epic parents.** [[MYLA-61]], [[MYLA-62]], [[MYLA-64]] to [[MYLA-67]] live in `Roadmap ideas/`, their children elsewhere. *Recommended:* each parent moves into its epic's folder with a `## Children` list.
- **Pull requests.** Options: one per task; one per epic step or review round, named after its tasks. *Recommended:* the second; one per task means a CI cycle per small fix, while today's large mixed PRs are hard to review, so the unit is one theme.
- **Evidence.** *Recommended:* `## Evidence` as the one heading, named in Conventions and checked by `scripts/check_tasks.py`.

## Decision

*Open.* The owner's answer goes here and, once given, onto [[Project/Decisions]] as a numbered decision.

- [ ] Decided, and recorded on [[Project/Decisions]]
- [ ] The implementation tasks created or updated to match
