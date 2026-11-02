---
id: MYLA-205
title: "Decision: how decisions are recorded (numbering, a provisional state, the page format)"
type: chore
status: review
priority: low
labels: [decision, docs, process]
---
From the October 2026 review ([[Project/Review-2026-10]], §11.4 and §13.6). D94, D96 and D97 were written on one day and D97 supersedes parts of D89 and D94: "locked" decisions superseded within hours read as session notes. [[Project/Decisions]] is also one 100-row table with cells of up to 2,600 characters ([[MYLA-193]] is the reformatting).

## Question

When does a choice get a decision number, and how is the page laid out?

## Options

- **A. As today**: a number as soon as a choice is made, one table.
- **B. A provisional state.** New decisions are numbered but marked *provisional* until the owner signs them off (in a review round, like tasks going from `review` to `done`); a provisional decision is edited in place rather than superseded by a new number.
- **C. Wait before numbering.** Choices live in the task until they have survived a day or a review, then get a number.

The format question is separate: one `###` heading per decision with number, date, status, decision, rationale and supersedes / superseded by, and a short index table at the top ([[MYLA-193]]).

## Recommendation

**B, with [[MYLA-193]]'s heading format.** It keeps the numbers stable for references while making clear what the owner has confirmed; the sign-off fits the review rounds that already exist. Choices an agent makes on its own are always provisional.

## Decision

**On hold (2026-11-01).** The owner: Genbeya will get a decision-management mechanism soon; until then decisions are recorded as today (a number at once, one table). [[MYLA-193]] waits for it too. No decision number.

- [x] Decided, and recorded on [[Project/Decisions]]
- [x] The implementation tasks created or updated to match
