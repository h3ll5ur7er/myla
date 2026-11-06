---
id: MYLA-243
title: The standard library inside the toolchain
type: feature
status: done
priority: high
labels: [stdlib, loader, cli, lsp, platforms]
---
The owner installed `myla` by symlinking `build/myla` into `/usr/bin` and ran `myla new` (2026-11-02). The stdlib had to be named with `--stdlib`, and the language server knew nothing of it. The tools look for `lib/` next to the `build/` directory of `argv[0]`, which a command found on the PATH doesn't name. A user who installs only the executable has no `lib/` at all. The owner's decision: the toolchain carries its standard library, in a way that works on every platform to come (Windows, wasm, D117).

- [x] **Embedded:** a module generated from `lib/` holds each std module's path and text, and the gdb script; `scripts/bootstrap.sh` regenerates it, CI fails when it isn't current (as for the seed, D101)
- [x] **Read from memory:** the loader takes the embedded modules as texts under a virtual root (`<myla>/std/io.my`), through the path that already serves an editor's unsaved buffers; no file is written, so it works where there is no file system (wasm); diagnostics and runtime errors name `<myla>/std/io.my:L:C` on every platform
- [x] **Overrides:** `--stdlib <dir>`, then `MYLA_STDLIB`, replace it with a directory (the repository's `lib/` while std is being changed); the guess from `argv[0]` goes
- [x] **`build -g`:** the gdb script from the embedded copy
- [x] **The language server:** completion, hover and diagnostics on the embedded texts; go-to-definition into std through a request (`myla/stdSource`) the VS Code extension shows as a read-only `myla-std:` document; the extension finds `myla` and `myla-lsp` on the PATH (and names the repository's `lib/` only inside the repository)
- [x] **The test first:** an installed layout (only the binaries, in a temporary prefix, reached through a symlink on the PATH, no repository, no `--stdlib`) where `myla new`, `run`, `test`, `build` and `build -g` work, and the language server completes `std.io` and opens a std definition
- [x] A decision row, and [[Getting-started]], [[Architecture/Module-loader]], [[Architecture/Editor-tooling]], [[Development/Bootstrap]] updated

## Evidence

- **The test first.** `tests/burn/test_installed.py` copies only `myla` and `myla-lsp` into a prefix and links them into a `bin/` on the PATH, as the owner did, with no `--stdlib` and no `MYLA_STDLIB`. Its five tests:
  - `myla new`, `run`, `test` and `build` of a project using `std.io`, `std.json` and `std.process`;
  - `build -g`, whose binary carries the pretty-printers;
  - an error in a call to std, and an unknown `std` module;
  - `--stdlib` and `MYLA_STDLIB` replacing the library with a directory (an empty `MYLA_STDLIB` doesn't);
  - the language server: no diagnostics, hover on `println`, its definition at `myla-std:/std/io.my`, the text from `myla/stdSource` equal to `lib/std/io.my`, `null` for a file std doesn't have.

  Before the change all five failed with the owner's error ("cannot resolve import 'std.io'"); after it they pass.
- **`std.process.env`** (two commits, because the seed compiles the interpreter and std):
  - First commit: the primitive `__getenv` in the checker, the lowering and the native runtime (scanning `__envp`, which every program keeps; errno 2 when unset), and the seed.
  - Second commit: the interpreter and `env(name) -> Option<str>`.
  - `test_env.py`: the interpreter and native code agree on a value containing `=`, an empty value, names that share a prefix, an unset name and an empty name.
- **The embedding.**
  - `tools/embed/main.my` writes `selfhost/embedded_std.my` from `lib/`: each file's text as one string literal, so the module is 63 lines and 90 KB. It writes only when the content changed and has a `--check` mode.
  - `scripts/bootstrap.sh` builds it with stage 0 and runs it before stage 1.
  - All eight files round-trip byte for byte.
  - A list of lines per file cost about 210 KB per binary; one literal per file costs about 93 KB (`myla` 1.87 → 1.97 MB, `myla-lsp` 1.10 → 1.20 MB).
  - `test_embedded_std.py` checks that the committed module is current, and that a change to `lib/` is noticed and written once.
  - `scripts/check-seed.sh` (CI's bootstrap job, the pre-push hook) fails when a bootstrap rewrote the committed module.
- **Reading from memory.**
  - [[selfhost/stdroot.my]]: the root `<myla>`, `is_embedded`, `embedded_text`, `stdlib_file`, and `default_stdlib_root` (`MYLA_STDLIB`, else `<myla>`).
  - The loader reads through `source_text`: an editor's buffer, then an embedded file, then the disk. No file is written.
  - `build -g` takes the gdb script from `stdlib_file`.
  - `main`, `gen_main`, `interp_main` and `myla-lsp` default to it; `interp_main` used to have no std without an argument.
- **The language server and the extension.**
  - `myla-std:` URIs map to `<myla>/…` and back.
  - The resolver and `file_text` read through `source_text`.
  - `myla/stdSource` serves only embedded files: no overrides, so no file on disk is read.
  - The extension shows `myla-std:` documents through a content provider, serves them to the server too, and finds `myla` and `myla-lsp` on PATH when there is no setting and no repository (a unit test, and `TestExtensionStartsTheServer.test_the_server_on_the_path`). In the repository it still names `lib/`, so std changes are seen before a bootstrap.
- **Verification.**
  - The burn suite passes in a clean checkout: 880 tests, 124 skipped. Compared with before, the 8 new skips are recordings about the compiler and std files this change touched; 5 more are the tree-sitter CLI, which the clean checkout lacks.
  - `check-seed.sh` fails, as it should, when `lib/` changes and a bootstrap rewrites the committed module.
  - The bootstrap reaches its fixed point; the seed is current.
  - The extension's typecheck, lint and tests pass (55; its activation test checks that the `myla-std` provider is registered).
- **After the owner tried it (2026-11-03).**
  - Symlinked `myla` and `myla-lsp` worked without `--stdlib`, and hover on imported functions worked.
  - Ctrl+click did nothing. The extension came from master's CI, so it had no `myla-std:` document provider; this branch's extension has one.
  - `from std.` completed only VS Code's words from the file: the server had no completion inside imports at all, for std or the project. It has now (`tools/lsp/imports.my`, see [[Architecture/Editor-tooling]]):
    - modules after `from`/`import` and each dot, by the loader's rules, the embedded library's from its list of files;
    - a module's public names, with their signatures, after `from <module> import`;
    - nothing after `as`.
  - Tests first: `test_modules_after_from_and_import` and `test_public_names_after_import` in the request scenarios (with the stdlib in a directory), and completion in `test_installed` (the embedded library). They failed with keywords and workspace words; with the change all 154 language server and installed tests pass, and `imports.my`'s 20 `#test` cases.
- **Docs and decision.** D118; [[Getting-started]], [[Architecture/Module-loader]], [[Architecture/Editor-tooling]], [[Architecture/Self-hosted-compiler]], [[Development/Bootstrap]], [[Language/Standard-library]] (`env`), `AGENTS.md` and the myla skill.
