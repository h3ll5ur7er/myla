---
id: MYLA-297
title: "CI gaps per target: the burn suite on aarch64 hardware, wasmtime, the browser page, missing binutils"
type: chore
status: backlog
priority: medium
labels: [ci, targets]
---
Found by the review of 6 November 2026 ([[Project/Review-2026-11]]).

- the burn suite cannot run on aarch64 hardware: `CAN_BUILD_NATIVE` requires x86-64 and `_tools._assemble` hard-codes `as --64`, so the `bootstrap-arm64` job runs only the examples and the stress programs, and a Raspberry Pi user has no suite; the page doesn't say so
- the `targets` job doesn't set `MYLA_REQUIRE_TARGETS`, and if binutils were missing every suite would skip and the job print "16 of 16 suites passed"
- `wasmtime` is a claimed host (D125, [[Language/Targets]]) and is installed nowhere; the WASI shim implements the 18 imports the programs use
- the browser page (`tools/wasm/myla.mjs`) is tested only where Playwright happens to be installed, never in CI
- the two peak-memory tests skip on wasm though the program's memory is readable as `memory.buffer.byteLength`
- `test_time`'s reactor programs run only under qemu, which can't reorder memory; they should run on the arm64 job with `scripts/stress-native.py` ([[MYLA-267]])

- [ ] Each item, or a documented decision not to (Node only)
