---
id: MYLA-554
title: "R12 Documentation and the board after round 5"
type: improvement
status: todo
priority: low
labels: [docs, board, round-6]
---
Work package R12 of [[Project/Review-2026-11-12]]. Files: `docs/`, `tasks/`, the `myla` skill. Follows [[MYLA-427]]. Known issues, the follow-up plan and the verdicts were brought in line with the review itself.

- [ ] `docs/Language/Standard-library/Bitset.md` line 98 and `Grid.md` line 96 give [[MYLA-353]], which is done, as the reason `for i in b` is missing (the sentence [[MYLA-427]] fixed on Set and Deque); with [[MYLA-553]]'s `iter()`
- [ ] `docs/Development/Testing.md` line 81: `#test` coverage is 1,447 of 2,295 functions, 63 percent, not 67
- [ ] Seven public helper methods on their pages, until [[MYLA-433]] can hide them: `args.check_name`, `args.check_option`, `bitset.past`, `csv.take_more`, `http.finish`, `http.reusable`, `net.took`
- [ ] `xs.sum(0)` and `iter.sum` overflow as the element's `+` does (a trap where checked, wrapping in a plain build); neither page says so
- [ ] What a `for` over a list or a map sees when its body changes it: the loop walks what it began with ([[MYLA-496]])
- [ ] The skill's `xs.mapped<str>(g)` reads like a list method; std.list has `map<U>`
- [ ] 25 `done` tasks have open boxes: [[MYLA-19]] and MYLA-36 to 51 (Rust edition) have none ticked, so do [[MYLA-151]], [[MYLA-161]] and [[MYLA-167]]; [[MYLA-133]], [[MYLA-168]], [[MYLA-171]], [[MYLA-187]], [[MYLA-254]] and [[MYLA-264]] have one or two. Tick what was done, or note what was dropped
- [ ] [[MYLA-288]], [[MYLA-296]] and [[MYLA-299]] are `in-progress` and untouched since 7 November: 288 lacks the token and AST expectation files, 296's open half is the native timer lock and not its title, 299's only open item duplicates [[MYLA-234]]. Back to `backlog`, renamed or closed, as the owner decides
- [ ] [[MYLA-435]] names `unwrap`, which doesn't exist, and has no reproducer (a failing `expect` prints `--> <myla>/std/option.my:79:26` on run, plain and `-g`); [[MYLA-504]]'s sizes have drifted (42,544 against 18,720 bytes today)
