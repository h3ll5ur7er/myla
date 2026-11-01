---
id: MYLA-193
title: Decisions page as one heading per decision
type: chore
status: backlog
priority: low
labels: [docs]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). [[Project/Decisions]] is a 97-row table with decision cells up to 2,600 characters and rationale cells up to 1,500 (12,800 words in one table), newest first, with "(1)…(4)" sub-numbering inside cells. It is the project's "why" and it can't be read in any Markdown renderer or searched by topic.

- [ ] One `###` heading per decision (number, date, title, decision, rationale, superseded by / supersedes), grouped by area or by date, with a short index table at the top
- [ ] A convention for decisions made and superseded on the same day (D94 → D96 → D97): a "provisional" marker, or waiting a day before numbering
- [ ] The references `D1–D58` across the wiki replaced by a link to the page

Waits for the decision in [[MYLA-205]].
