---
id: MYLA-792
title: "R7-3 Interpreter and harness: generic #track_caller (H6), the record race (M2), a deferred block's verdict (M12), imported constants (H13), a case's time limit"
type: bug
status: todo
priority: high
labels: [interpreter, testing, round-7]
---
Work package of [[Project/Review-2026-11-17]], lane "Interpreter and harness" (section 5). Files: `selfhost/interp.my`, `selfhost/harness.my`, `lib/std/test.my`, `lib/std/rt.my` (the test record's functions only; the HTTP lane owns `exec_run`). The reproducers are in the review's bundle (`repro-r6/`, with a README per area); each fix turns its reproducer into a test that fails before it. The owner's decisions it builds as the review recommends: 5. New tasks it files take ids 817–824.

- [ ] **H6** (high, new): a generic `#track_caller` function: `lt(18446744073709551615u64, 2u64)` is `true` interpreted, `false` natively; `%caller` takes the frame's first slot, where `%env` is looked for (named frame slots). `repro-r6/interp-harness/track_caller_generic.my`. Reopens [[MYLA-435]]
- [ ] **M2**: D191's record is three writes, so a worker's `eprint` cuts it (a test with noisy tasks passes 8/8 interpreted, 0–8/8 natively); a case that writes a `P:0;` record with the nonce from its arguments and is then killed passes. `repro-r6/interp-harness/record_race.my`, `forged_record.my`. Reopens [[MYLA-547]]
- [ ] **M12**: a deferred block that fails as a test case returns: pass natively, fail interpreted. `repro-r6/interp-harness/defer_verdict.my`
- [ ] **H13** (high, old): `const C: int32 = BAD_HANDLE` (an imported constant) is 0 interpreted and 34 natively. Fix [[MYLA-715]]. `repro-r6/docs/known_715_const.my`
- [ ] Decision 5: a time limit for a test case (build [[MYLA-547]]'s third proposal, `--timeout` with a default), and kill the child's process group when the runner dies
- [ ] [[MYLA-546]]/[[MYLA-565]]'s follow-up: start-up crept from 24.0 M to 35.7 M instructions (with [[MYLA-796]]'s lazy `std.float`); a run-time spec that doesn't fit is ignored
- [ ] Low: a test child's `process.args()` holds the harness's arguments; `[StringBuilder(b'')]` against `[<StringBuilder>]` in a report
