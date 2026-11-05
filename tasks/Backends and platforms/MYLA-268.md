---
id: MYLA-268
title: "Every suite on every target, and CI that fails when a target's tools are missing"
type: improvement
status: backlog
priority: medium
labels: [testing, ci, platforms]
---
Found by [[Project/Reflection-2026-11]]. Only x86-64 is held to the full suite. The other targets each run a small hand-made program list against the x86-64 build:
- `test_aarch64.py`: the examples, 11 programs, the stress programs, test_time's programs, stack overflows;
- `test_wasm.py`: the examples, the same programs, files, the stress programs, the page API.

The parity programs, the native runtime errors, the error corpus's runtime cases, and the I/O and feature suites don't run on them. The compiler's self-compile is tested on `examples/maps.my` only.

Both modules also skip silently when a tool is missing, so CI can go green without having run them. `scripts/test.sh`'s fast run includes them, though they take minutes.

- [ ] A target parameter in the test harness (`_native.py`: build, run and emulator per target), so the parity, runtime-error, error-corpus and I/O suites run per target, with the per-target exceptions listed in one place ([[MYLA-266]])
- [x] The full self-compile per target in CI (the compiler built for the target compiles the compiler: the same assembly). aarch64: CI's `bootstrap-arm64` job runs the bootstrap on arm64 hardware, stages 0 to 3 to the fixed point, and checks that the aarch64 compiler writes the x86-64 seed byte for byte. wasm32: `test_wasm.WasmParity.test_the_compiler_compiles_itself` (2026-11-05), the compiler built for wasm under Node compiling `selfhost/gen_main.my` for wasm32 and x86-64, byte for byte the native compiler's, in about 17 s.
- [x] CI fails when it lacks a target's tool instead of skipping; `test_aarch64` and `test_wasm` in `test.sh`'s slow list (2026-11-05: `MYLA_REQUIRE_TARGETS`, set by CI's burn job, makes `Aarch64Tools`/`WasmTools.test_the_tools_are_there` fail when a tool is missing, checked with an empty `PATH`; the stress programs run on arm64 hardware through `scripts/stress-native.py`, [[MYLA-267]])
