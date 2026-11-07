---
id: MYLA-297
title: "CI gaps per target: the burn suite on aarch64 hardware, wasmtime, the browser page, missing binutils"
type: chore
status: review
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

- [x] Each item, or a documented decision not to (Node only)

## Evidence

- The burn suite on aarch64 hardware: not made to run (its native builds assume x86-64, `CAN_BUILD_NATIVE` and `as --64`); [[Development/Testing]] says so in the `bootstrap-arm64` row, and what runs there instead: the examples, the stress programs and the new litmus programs.
- `targets` job: `MYLA_REQUIRE_TARGETS` set, and `scripts/test-target.py` checks the target's tools before anything runs (`missing_tools`: `as`, `ld` and clang, `ld.lld`, `qemu-aarch64` or clang, `wasm-ld`, `node`): with the variable set a missing one fails (`wasm32-wasi: missing node: the suites would skip`, exit 1, tried with Node off the PATH), without it a warning.
- wasmtime (D158): Node is the tested host; [[Language/Targets]] says another WASI host should run the programs but nothing checks it.
- The browser page: a CI job `wasm-page` installs Playwright with its Chromium and runs `test_wasm.WasmBrowser` with `MYLA_REQUIRE_BROWSER`, under which the new `BrowserTools` test fails instead of the page's test skipping. The page's test passes here (6 s).
- The peak-memory tests on wasm: `run.mjs` writes the linear memory's size at the end to `MYLA_WASM_MEMORY_OUT` (a wasm memory only grows, so that is its peak), and `_build_and_measure` uses it on wasm32. `test_stress_programs_reclaim_memory` runs there now and passes its 30 MB bound; `test_deep_task_trees_and_awaits` stays excused with the measured reason: its linear memory is 80 MB, as a 16 MiB chunk counts whole once used and the 8 MiB shadow stack counts, where natively 18 MB of pages are touched.
- `test_time`'s reactor on arm64 hardware: the litmus programs of [[MYLA-301]] (timers, cancelled sleepers, watched pipes) run 1,000 times each on 4 and 16 workers in `bootstrap-arm64`, through `scripts/stress-native.py`.
