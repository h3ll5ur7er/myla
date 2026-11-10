---
id: MYLA-397
title: "A target's own platform module can't be tested on that target"
type: bug
status: todo
priority: low
labels: [testing, harness, platforms]
---
Found by the test-harness batch ([[MYLA-370]]). `MYLA_EMULATOR="node tools/wasm/run.mjs" build/myla test lib/std/platform_wasm.my --target wasm32-wasi` fails with "more than one '#main' entry point" (at `lib/std/platform.my:1090`) and the harness doesn't build: on wasm32 that file is `std.platform`, which the harness imports too (through `std.test`), so the module comes in twice. The same holds for `platform_aarch64.my` under qemu. `test_std_modules` leaves the platform modules out on the targets for this reason.

- [x] The harness (or the loader) treats the tested file and the target's `std.platform` as one module when they are the same file; each platform module's cases on its own target in `test_std_modules`

## What was built

- **The harness side** ([[selfhost/driver.my]]): `native_tests` builds the harness from `harness_entry(file, stdlib_root, target)`: the standard library's `std/platform.my` when the tested file is the target's own platform module, else the file. `for_target` gives that path the tested file's text, which is the harness's (the override), so the tested module and the `std.platform` the harness imports (through `std.test`) are one module, the entry. Paths are compared absolute and normalized; with the library the tools carry (no `--stdlib`) the file is outside it and loads as before. `selfhost/project_cmd.my`'s `myla test --native` goes through `native_tests` too.
- **The loader**: only `target_platform_file(target)` (`platform_aarch64.my`, `platform_wasm.my`, `""`), which `for_target` now uses and the driver shares.
- **wasm32's start** ([[selfhost/runtime_wasm.my]]): the prelude called `std$platform$wasm_start` and `std$platform$map_memory` by their qualified names; with std.platform the entry its names are unqualified (the loader's rule for an entry file), so `platform_fn` takes the unqualified one when the qualified one isn't there. Without it the harness built and the compiler stopped with `internal error: wasm: myla_std$platform$wasm_start (…) takes 2 words, called with 0`.
- **`test_std_modules`**: on a target its own platform module runs (`OWN_PLATFORM`), and `test_modules_are_found` says which.
- [[Language/Attributes-and-testing]] says how such a harness is built.

One thing to know: as the entry, the platform module's names are unqualified, so the checked harness build (D175) puts overflow checks in its functions, which `checked_code` leaves out of `std$platform$…`. Its cases pass on both targets; a case that relied on wrapping arithmetic there would see `integer overflow` under `myla test --target` only.

## Evidence

Built on `9681bb3` (after [[MYLA-399]] and [[MYLA-405]] in the streams lane).

- **Before:** `MYLA_EMULATOR="node tools/wasm/run.mjs" build/myla test lib/std/platform_wasm.my --target wasm32-wasi --stdlib lib`: `type error: more than one '#main' entry point --> lib/std/platform.my:1138:1`, `myla: the test harness of lib/std/platform_wasm.my didn't build`; `build/myla test lib/std/platform_aarch64.my --target aarch64-linux --stdlib lib` (qemu): the same at `lib/std/platform.my:2044:1`. After the driver change alone, wasm32 built the harness and the compiler stopped at the start's call (above).
- **After:** wasm32 (Node) `13/13 passed.`; aarch64 (qemu) `23/23 passed.`; with an absolute path to the file too. `harness_entry`'s six cases and `target_platform_file`'s three.
- **Bootstrap:** byte-identical fixed point, 19,371,251 bytes.
- **Suites:** `scripts/test-target.py wasm32-wasi test_std_modules` (now with `platform_wasm`): OK (49 s); the host's slow suites with `test_std_modules`, `test_selfhost_cases`, `test_compiler_parity`: 799 tests OK; on aarch64 `test_std_modules` stays excused (`_targets.py`: a qemu process per case takes minutes), so the run above is the evidence there.

## Review 2026-11-10

Not ready ([[Project/Review-2026-11-10]]): works only when the file and the library root are spelled the same way: `./lib/std/platform_aarch64.my`, `--stdlib lib/` and `MYLA_STDLIB=$PWD/lib` give 0/23 or an internal error (S3). The fix is in [[MYLA-418]].

- [ ] The review's blocker, fixed with [[MYLA-418]]
