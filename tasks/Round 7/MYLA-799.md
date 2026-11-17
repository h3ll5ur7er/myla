---
id: MYLA-799
title: "R7-10 Website: the skip link, the phone layout, lost output, the storage value, the reference"
type: bug
status: todo
priority: medium
labels: [website, round-7]
---
Work package of [[Project/Review-2026-11-17]], lane "Website" (section 5). Files: `website/`. The reproducers are in the review's bundle (`repro-r6/`, with a README per area); each fix turns its reproducer into a test that fails before it. No owner's decision. New tasks it files take ids 877–884.

- [ ] [[MYLA-630]] (reopened): the skip link goes to the home page on every deep route; `/quickstart` scrolls sideways on a phone; CodeMirror is 376 kB, not the 66 kB the task states
- [ ] **M16**: output printed before a time-out or Stop is lost; recursion is ten times shallower than native (250 against 2,400) and says so nowhere; `{"version":1,"solved":null}` in the browser's storage breaks the learn area, and Import accepts it; 26 reference signatures drop default values; seven docs examples offer Run and can't work in a browser ([[MYLA-631]] to [[MYLA-634]])
- [ ] A build that fails on a dead link
- [ ] Low: links to `/reference/rt` and `/reference/slice`; `#track_caller`'s anchor is dead; the Windows twins listed as modules; muted text below WCAG AA; the course says an async `main` needs `#main`; four exercises accept a wrong answer; `website/test-results/.last-run.json` is committed
- [ ] Not run in round 7's lanes: another agent develops the website meanwhile; this package waits for the owner
