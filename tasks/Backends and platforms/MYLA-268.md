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
- [ ] The full self-compile per target in CI (the compiler built for the target compiles the compiler: the same assembly)
- [ ] CI fails when it lacks a target's tool instead of skipping; `test_aarch64` and `test_wasm` in `test.sh`'s slow list
