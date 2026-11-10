---
id: MYLA-418
title: "P4 The test harness: failing reports agree across runners"
type: bug
status: todo
priority: high
labels: [test-runner, harness, round-5]
---
Work package P4 of [[Project/Review-2026-11-09]] (wave A1), with round 4's additions from [[Project/Review-2026-11-10]]. Files: `selfhost/harness.my`, `lib/std/test.my`, `selfhost/driver.my`, `selfhost/loader.my`, `tests/burn/test_test_native.py`, `tests/burn/test_std_modules.py`. Reopens [[MYLA-361]] and [[MYLA-397]].

- [ ] M6: `exit(0)` in a case is not a pass natively; `[exit(0)]` passes
- [ ] M7: a failing float is reported as the interpreter does (`2.0`)
- [ ] M8: a test function returning `Result<(), E>` with a scalar `E` builds its harness natively ([[MYLA-361]])
- [ ] M9 and D183: an expected `[panic(…)]` matches exactly, natively as interpreted
- [ ] A case's stderr is reported the same way by both runners
- [ ] Burn tests that hold failing reports to both runners: a float, `exit(0)`, a scalar `Err`, stderr, expected panics
- [ ] S3: `native_tests` and `for_target` key the override on a normalized path (`./lib/std/…`, `--stdlib lib/`, `MYLA_STDLIB=$PWD/lib`), with a burn test per spelling ([[MYLA-397]])
- [ ] `myla test lib/std/<m>.my` without `--stdlib lib` loads one copy of each module (option, bench, log, net, time, yaml loaded two)
- [ ] `test_std_modules` asserts case counts, and runs `platform_aarch64` and `platform_wasm`'s 36 cases interpreted ([[MYLA-325]])
- [ ] The lazy parity test fails on a `lib/std` file that reports `same 0` ([[MYLA-359]])
- [ ] A module-id collision is reported with a location
- [ ] A burn test that times out leaves a core dump or the child's stack, for the rare aarch64 hang under qemu ({R2} §1.6)
- [ ] D183: the parity tests compare stderr
