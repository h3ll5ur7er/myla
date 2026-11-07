---
id: MYLA-370
title: "wasm32: the native test harness stops at the first case that expects a panic"
type: bug
status: todo
priority: medium
labels: [testing, wasm, harness]
---
Found by the `std.args` lane ([[MYLA-333]]). `myla test --target wasm32-wasi` ran 20 of `std.args`'s 26 cases: the first case expecting a runtime error (`[panic("…")]`, D162) ended the run there, where x86-64 and aarch64 run all 26. wasm32 has no way to catch a trap inside the module, so the harness needs another way to run such a case: each expected-failure case as a run of its own (the harness started once per case), or the expected panic checked by the host from the exit and the message.

- [ ] Every case runs on wasm32, expected failures included; a failing case doesn't end the run
- [ ] `test_test_native`'s wasm32 tests cover a `[panic(…)]` case followed by ordinary ones
