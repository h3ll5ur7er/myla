---
id: MYLA-243
title: The standard library inside the toolchain
type: feature
status: in-progress
priority: high
labels: [stdlib, loader, cli, lsp, platforms]
---
The owner installed `myla` by symlinking `build/myla` into `/usr/bin` and ran `myla new` (2026-11-02). The stdlib had to be named with `--stdlib`, and the language server knew nothing of it. The tools look for `lib/` next to the `build/` directory of `argv[0]`, which a command found on the PATH doesn't name. A user who installs only the executable has no `lib/` at all. The owner's decision: the toolchain carries its standard library, in a way that works on every platform to come (Windows, wasm, D117).

- [ ] **Embedded:** a module generated from `lib/` holds each std module's path and text, and the gdb script; `scripts/bootstrap.sh` regenerates it, CI fails when it isn't current (as for the seed, D101)
- [ ] **Read from memory:** the loader takes the embedded modules as texts under a virtual root (`<std>/io.my`), through the path that already serves an editor's unsaved buffers; no file is written, so it works where there is no file system (wasm); diagnostics and runtime errors name `<std>/io.my:L:C` on every platform
- [ ] **Overrides:** `--stdlib <dir>`, then `MYLA_STDLIB`, replace it with a directory (the repository's `lib/` while std is being changed); the guess from `argv[0]` goes
- [ ] **`build -g`:** the gdb script from the embedded copy
- [ ] **The language server:** completion, hover and diagnostics on the embedded texts; go-to-definition into std through a request (`myla/stdSource`) the VS Code extension shows as a read-only `myla-std:` document; the extension stops passing `--stdlib` and finds `myla-lsp` on the PATH
- [ ] **The test first:** an installed layout (only the binaries, in a temporary prefix, reached through a symlink on the PATH, no repository, no `--stdlib`) where `myla new`, `run`, `test`, `build` and `build -g` work, and the language server completes `std.io` and opens a std definition
- [ ] A decision row, and [[Getting-started]], [[Architecture/Module-loader]], [[Architecture/Editor-tooling]], [[Development/Bootstrap]] updated
