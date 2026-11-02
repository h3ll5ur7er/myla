---
id: MYLA-214
title: "Decision: board and process rules (done, task types, epics, pull requests)"
type: chore
status: review
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

**`done` (2026-11-01):** agents put tasks into `review` when they are done; the owner moves them to `done`, or asks for it explicitly, as until now (written into [[Development/Conventions]]). **The rest (2026-11-01): the recommendations, except the `decision` type.** The owner: Genbeya will get its own convention for decisions, neither as tasks nor in the wiki, so no `decision` type: the invalid types are recoded (`design` and `test` as `chore`). Epic parents move into their epics' folders with a `## Children` list; one pull request per theme (an epic step or a review round), named after its tasks; `## Evidence` is the one evidence heading (both rules written into [[Development/Conventions]]). Implementation: [[MYLA-194]]. Process rules, so no decision number.

- [x] Decided, and recorded in [[Development/Conventions]] and here
- [x] The implementation tasks created or updated to match
