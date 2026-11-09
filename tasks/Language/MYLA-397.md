---
id: MYLA-397
title: "A target's own platform module can't be tested on that target"
type: bug
status: backlog
priority: low
labels: [testing, harness, platforms]
---
Found by the test-harness batch ([[MYLA-370]]). `MYLA_EMULATOR="node tools/wasm/run.mjs" build/myla test lib/std/platform_wasm.my --target wasm32-wasi` fails with "more than one '#main' entry point" (at `lib/std/platform.my:1090`) and the harness doesn't build: on wasm32 that file is `std.platform`, which the harness imports too (through `std.test`), so the module comes in twice. The same holds for `platform_aarch64.my` under qemu. `test_std_modules` leaves the platform modules out on the targets for this reason.

- [ ] The harness (or the loader) treats the tested file and the target's `std.platform` as one module when they are the same file; each platform module's cases on its own target in `test_std_modules`
