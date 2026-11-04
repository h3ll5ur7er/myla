---
id: MYLA-274
title: "A non-reentrant actor method kind"
type: feature
status: backlog
priority: low
labels: [concurrency, language, design]
---
Split off [[MYLA-171]], whose last item ("Consider a non-reentrant method kind … left for the owner") was never filed. D95 warns when an actor's state is changed across an `await`. A method kind whose calls queue until it returns, as Swift has discussed for actors, would let a method keep its invariants across an `await` without re-checking. A design round first, recorded as a decision (D107 left it for "a program that needs it").

- [ ] The proposal: syntax, what it costs the executor, deadlock rules (a non-reentrant method awaiting its own actor)
