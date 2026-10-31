---
id: MYLA-194
title: Validate the task board in CI; one evidence heading; the task types
type: chore
status: backlog
priority: low
labels: [repository, genbeya]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). The board is in good mechanical shape (159 tasks, every one parses, ids match file names, no broken references), and a script keeps it that way. Found on 2026-10-31:

- three invalid `type` values (`test` on [[MYLA-144]], `design` on [[MYLA-160]] and [[MYLA-166]]; `.genbeya.yml` has no `types:`, so the valid ones are `bug`, `feature`, `improvement`, `chore`): add `types:` to `.genbeya.yml` (the owner's call) or recode them
- the evidence convention has three shapes (`## Evidence`, `## Outcome`/`## Results`, inside the checklist); [[Development/Conventions]] names no heading
- 17 `done` tasks keep unticked items (mostly superseded closures); number gaps 90, 91, 112–115, 117, 118 are unexplained
- epic parents ([[MYLA-61]], [[MYLA-62]], [[MYLA-64]] to [[MYLA-67]]) live in `Roadmap ideas/` while their children live in their own epics

- [ ] `scripts/check_tasks.py` (front matter, statuses, types, id vs file name, unticked items in `done`, missing evidence) run by the `unit` CI job
- [ ] `## Evidence` as the one heading, named in Conventions; the three other shapes retitled
- [ ] The types, the gaps and the epic parents settled
