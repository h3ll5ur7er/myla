---
id: MYLA-700
title: "Windows step 1: a target record, and each target's tools named by it"
type: feature
status: review
priority: high
labels: [platforms, windows]
---
A step of [[MYLA-165]], the Windows target, in the plan the owner accepted on 2026-11-14 ([[Project/Follow-up-plan#windows-2026-11-14]]). The part of [[MYLA-262]] the port needs before it starts: the targets are strings today, and the driver runs the tools through `/usr/bin/env`, which Windows lacks.

- [x] A `Target` record (operating system, architecture, object format, executable suffix, the tools to assemble and link) in place of the target string, with `x86_64-windows` recognised by `--target`
- [x] The driver runs each target's tools by the record, without `/usr/bin/env`; a missing tool is named in the error ([[MYLA-262]])
- [x] Behaviour unchanged for the three targets there are: the bootstrap's fixed point and the suites the proof

## What changed

- **The record:** [[selfhost/target.my]] holds `Target` (name, `Os`, `Arch`, `ObjectFormat`, the programs' file suffix, the platform module, the tools from any machine (`cross`) and on the target's own (`native`), the emulator, whether its programs start processes, whether `-g` works, whether the compiler builds for it yet) and `Toolchain` (the command lines to assemble, to make import libraries and to link, with `{asm}`, `{obj}`, `{out}`, `{def}`, `{lib}` for the files, and what they need, for the error). `targets()` is the one list; `parse_target` is the one place a name is read, `host()` the machine's (`std.platform.TARGET`).
- **Who takes it:** `main.my` (`--target`, the usage, the default `-o`), `gen_main.my`, the driver (`compile_asm`, `native_tests`, `emulator`, `build_commands`, `cmd_build`), the project tool (`project_build`, `project_test`, the test programs), the loader's `for_target` (by `Target.platform_file`; `target_platform_file` is gone) and the code generator (`CodeGen.set_target`, which sets `a64`/`wasm` from the architecture; the booleans and the three-way chains stay, [[MYLA-262]]'s second part).
- **`x86_64-windows`:** known to `--target` and `gen_main --target`, and refused before anything is loaded or generated: `myla: building for x86_64-windows is not supported yet (MYLA-702)`, exit 1 (`gen_main: …`, exit 2), for `myla build`, `myla test --target`, and a project's `build` and `test`. Its tools are written in the record (D210): `clang --target=x86_64-pc-windows-msvc -c`, `llvm-dlltool -m i386:x86-64 -d {def} -l {lib}`, `lld-link /nologo /subsystem:console /entry:_start /nodefaultlib /out:{out} {obj} {lib}`, which assembled, made `kernel32.lib` and linked a PE32+ console executable from a ten-line GAS file calling `ExitProcess` on this machine (LLVM 18). Nothing uses `imports` yet: the list of functions per DLL is [[MYLA-702]]'s.
- **The tools:** the driver runs them with `std.process.run`, which searches PATH itself (`std.rt`, D147): no `/usr/bin/env` was left in the driver at BASE, and none is in the tools now (`grep -rn /usr/bin/env selfhost tools lib` finds only scripts' shebangs). A missing tool is named with the target and the record's `needs`: `myla: 'wasm-ld' was not found: building for wasm32-wasi here needs clang and wasm-ld`; lld-link's is the same path once Windows builds.
- **Docs:** [[Getting started]] lists each target's tools in a table; [[Language/Targets]] has the Windows row; [[Architecture/Self-hosted-compiler]] has `target.my`; the `myla` skill's toolchain reference (both copies).

## Proposals (open for the owner)

1. **Windows' programs start no processes in the record (`spawns: false`) until [[MYLA-705]].** A test harness then runs its cases as runs of itself (as on wasm32, [[MYLA-370]]), so [[MYLA-702]]'s first `myla test --target x86_64-windows` needs no `CreateProcess`. Alternative: `true` now, and the harness's cases wait for [[MYLA-705]]. Recommended: `false`, flipped by [[MYLA-705]].
2. **The default output on Windows is `a.exe`, a project's `build/<name>.exe`** (the record's suffix; `a.out` elsewhere, as before). Alternative: `a.out` everywhere, which Windows doesn't run by double-click or `PATHEXT`.
3. **Windows' platform module is to be `std/platform_windows.my`** (named in the record, never read while the target is refused). Alternative: a directory per target (`std/platform/windows.my`), which [[MYLA-701]] may prefer.
4. **The refusal comes first**, before the program is loaded or checked, so a Windows build of a broken program says it isn't supported rather than listing its errors. Alternative: check first, refuse at generation.

## Evidence

- **Test first:** `tests.burn.test_selfhost_cli` gained `test_windows_is_a_target_not_built_yet` (failed before: `myla: unknown target 'x86_64-windows'`; passes after) and `test_build_without_the_linker_on_path` (clang but no wasm-ld on PATH: the linker and the target are named; passed before too, a guard). `selfhost/target.my`'s cases (5/5) and `driver.my`'s (30/30, `each_target_has_its_tools` holds the four Linux and wasm command lines BASE had) pass; `loader.my` 167/167, `main.my` 1/1.
- **The fixed point:** `scripts/bootstrap.sh` reached it (27,880,618 bytes); `scripts/check-seed.sh build`: the committed seed bootstraps these sources, so no seed is staged (D207).
- **Same output:** BASE's `stage3` and the new one write byte-identical assembly for `selfhost/gen_main.my` (the whole compiler) and `examples/maps.my` with `--target` `x86_64-linux`, `aarch64-linux` and `wasm32-wasi` (six pairs, sha256 of the compiler's x86-64 output `6a1cc3cd1408…`); BASE's `myla build` and the new one write byte-identical files for `examples/maps.my` on all three targets.
- **Suites:** `scripts/test-target.py aarch64-linux`: 37 of 37 suites passed; `MYLA_EMULATOR="node tools/wasm/run.mjs" scripts/test-target.py wasm32-wasi`: 37 of 37; `scripts/test.sh fast`: 938 tests OK (3 skipped); `scripts/test.sh` (full): 1,703 tests, one failure, `test_lsp`'s `test_the_corpus_resolves` on `target.my`'s `format(...)` calls beside its field `format` (the language server's quirk, filed as [[MYLA-710]]): with f-strings there, `tests.burn.test_lsp.TestResolutionCorpus` passes, the bootstrap reaches its fixed point again and the six outputs are still the same.
