---
id: MYLA-336
title: "New platform primitives: entropy, file descriptors, pipes"
type: feature
status: todo
priority: medium
labels: [platforms, primitives, stdlib, wave-1]
---
Wave 1 of [[Project/Standard-library-roadmap]]. One task for every primitive that waves 3 and 4 need (sockets, terminals and signals excepted), so the platform layer and the seed's staging commit (D156) change once rather than in three lanes. It belongs to the platform track and runs alone.

- **Owns:** `lib/std/platform.my`, `lib/std/platform_aarch64.my`, `lib/std/platform_wasm.my`, `selfhost/` (the primitive tables, the interpreter, the three backends)
- **Needs:** nothing; it can start as soon as its wave does

- [ ] Entropy: `__random_bytes(n)` (`getrandom`; WASI `random_get`)
- [ ] File descriptors: open with flags and a mode, read and write at the cursor, seek, close, fstat (size, mode, modification time); the `IoError` causes as today
- [ ] Pipes and children: spawn with pipes for stdin, stdout and stderr; read and write them; wait; kill. On wasm32 `Unsupported`
- [ ] Each on x86-64, aarch64 and wasm32 and in the interpreter; the per-target suites ([[MYLA-268]]) run them
- [ ] [[Language/Targets]] updated with the new capabilities
