---
id: MYLA-421
title: "P7 Regex: the lazy DFA and a differential job"
type: bug
status: todo
priority: high
labels: [std, regex, round-5]
---
Work package P7 of [[Project/Review-2026-11-09]] (wave A2). Files: `lib/std/regex.my`, its corpus. Reopens [[MYLA-335]].

- [ ] H10: fix the DFA, or send a pattern with an assertion inside a repetition to the Pike VM; `find` and `captures` of one call agree
- [ ] Long-text cases (96 bytes and more) in the corpus
- [ ] A differential job against Go's or Python's regex, from the review's oracle, as a burn test that runs when the oracle is installed
