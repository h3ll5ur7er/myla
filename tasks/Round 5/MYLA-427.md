---
id: MYLA-427
title: "P13 Documentation and the board"
type: chore
status: todo
priority: medium
labels: [docs, board, round-5]
---
Work package P13 of [[Project/Review-2026-11-09]] (wave A2), with round 4's additions from [[Project/Review-2026-11-10]]. Files: `docs/`, `tasks/`. The decisions themselves (D178 to D187) and the sign-offs were recorded with the reviews.

- [ ] The stale sentences of §3.3: `Types.md:42` (tuples can't be compared), `Heap.md:89`, `Option.md`'s lambda note ([[MYLA-324]]), `Int.md` and `Char.md` line 3, the Set, Deque and Heap pages on MYLA-353 and iterators ([[MYLA-330]]), `Url` and `Eq`
- [ ] [[Project/Known-issues]]: remove the 20 tasks that are done
- [ ] Undocumented `pub` items (`fmt.spec_need`, `io.errno_text`, methods on a dozen pages); runnable blocks for Fmt, Rt, Slice, Test and the four pages [[MYLA-325]] names; the Regex, Time and Io pages with the reference part first
- [ ] Evidence counts in task files and pages that later refactors changed
- [ ] D178 in [[Language/Methods-and-traits]] with the call-site error once [[MYLA-417]] builds it
- [ ] D179 in [[Development/Conventions]]: library editors run `myla test` on the module they changed
- [ ] D180: Net.md's line-protocol example and the warning that `buffered(s)` blocks its worker
- [ ] Io.md, Fs.md and Process.md: performance sections as current numbers, not histories of `read_str` measurements
