---
id: MYLA-547
title: "R5 The test harness: verdicts that still differ between runners"
type: bug
status: todo
priority: medium
labels: [testing, harness, round-6]
---
Work package R5 of [[Project/Review-2026-11-12]]. Files: `selfhost/harness.my`, `lib/std/test.my`, the interpreter's runner. Follows [[MYLA-418]]. The first box builds the owner's decision 1, D191 (2026-11-12): a framed record the runtime writes in a test child.

- [ ] **A multi-line panic is cut natively** (new with [[MYLA-418]], against D183): a message with a later line that starts `runtime error: ` is cut at that line on x86-64, aarch64 and wasm32, so `#test("a\nruntime error: b")[panic("a\nruntime error: b")]` passes interpreted and fails natively, `[panic("b")]` the reverse, and a failing test function shows only the tail (`repro-r5/harness/multiline_panic.my`). Stderr alone can't tell this from an `eprint` followed by a panic. Recommended: the runtime marks its own report in a test child (D189's proposal 1, taken up again), which also closes the forged marks below
- [ ] **An empty `Err` passes** (old): a test function that returns `Err("")`, or an error whose `Format` gives `""`, is `PASS` on every runner, because `detail == ""` means "passed" in `lib/std/test.my` and in the interpreter's runner. Carry the verdict separately (`err_empty.my`)
- [ ] **Exit statuses** (old): `#test(256)[exit(0)]` fails interpreted and passes natively, `[exit(256)]` the reverse, and `exit(-1)` is -1 interpreted and 255 natively. Mask to 0 to 255 in the interpreter's runner, or refuse an expected status outside it (`exit_range.my`)
- [ ] `Err(())` is shown as `()` interpreted and `None` natively; an `Err` of a closure as `VClosure(, false)` and `<function>` (`err_unit.my`)
- [ ] An interpreted case inherits `myla test`'s stdin and a native case gets an empty one: `echo x | myla test` fails interpreted and passes natively, and with an open stdin the interpreted run blocks (`stdin_case.my`). Decide whether a case gets a time limit
- [ ] A case that writes the protocol's marks on stderr and then calls `exit(3)` passes natively; one that prints the case mark shifts the next verdicts on wasm32 (`proto.my`)
- [ ] `myla test lib/std/rt.my --native` ends in `internal error: no function 'std$rt$alloc_tasks' to compile`; the exclusion is known and should be a message
- [ ] `docs/Language/Attributes-and-testing.md`, line 200: "an index error or a missing map key can be expected interpreted only" is no longer true
