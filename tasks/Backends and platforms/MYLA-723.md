---
id: MYLA-723
title: "The interpreter, myla check and the language server load the host's own modules"
type: bug
status: review
priority: low
labels: [platforms, windows, loader]
---
Found by [[MYLA-704]]. `for_target` ([[selfhost/loader.my]]) gives a target its own `std/platform.my` and, since MYLA-704, its own copies of other modules (`std/path_windows.my` for `std/path.my`, `std/path_style_windows.my` for `std/path_style.my`). Only a native build and a native test harness call it (`compile_asm`, `native_tests` in [[selfhost/driver.my]]); `myla run`, `myla test` interpreted, `myla check`, the REPL and the language server load `std/platform.my`, `std/path.my` and `std/path_style.my` as they are, which are Linux's.

On Linux that is right (the host is x86-64 Linux, whose `platform_file` is ""). A `myla.exe` built for Windows ([[MYLA-702]], [[MYLA-709]]) interprets a program with Windows' primitives (the CLI's own std.rt is Windows') but Linux's std.path: `path.parent("C:\\a\\b")` is `""` there, and `std.platform.TARGET` says `x86_64-linux`.

To reproduce, on Linux: `myla build --target x86_64-windows selfhost/main.my -o myla.exe`, then under Wine `myla.exe run p.my` with `p.my` printing `path.parent("a\\b").unwrap_or("none")` gives `` (Windows' rules give `a`).

- [x] The commands that load a program for the host (`run`, interpreted `test`, `check`, `repl`, the language server) load it with `for_target(opts, host())`; a test that a program interpreted by a CLI built for Windows reads Windows' std.path

## What changed

**The loader** ([[selfhost/loader.my]]): `for_host(entry, opts)` is `for_target(opts, host())`, with one exception: a module a copy replaces (`std/platform.my`, `std/path.my`, `std/path_style.my` of the root) is itself when it is the entry, so `myla test lib/std/path.my` runs path.my's cases on every host, as a native harness keeps a module the caller gives a text of its own (`own_copy`). `same_file` compares the entry with the module's path, normalized and from the working directory where one of them is relative. On x86-64 Linux `for_target` changes nothing (its `platform_file` is ""), so neither does this; on aarch64 Linux the interpreter now reads `platform_aarch64.my` (`TARGET` is `aarch64-linux` there too).

**The commands.** The driver's `load_for_host` ([[selfhost/driver.my]]) is `load_and_check` after `own_library` has chosen the root and `for_host` the modules; `cmd_interp` (`myla run`), `cmd_test` (`myla test` interpreted), `own_tests` (a project's files), `myla check` ([[selfhost/main.my]]) and a project's `myla check` ([[selfhost/project_cmd.my]]) take it. The REPL ([[selfhost/repl.my]]) loads each input with `for_host`, the language server ([[tools/lsp/server.my]]) a document it checks for its diagnostics. A build (`compile_asm`) and a native harness keep `for_target` with their target.

Left as they are: the language server's other requests (hover, definitions, completion) read a module's file as it is, which is where an editor shows it: with the copy's text under `std/path.my`'s name a definition would point at the copy's lines in the other file. The developer tools `interp_main.my`, `check_main.my` and the playground's `play_main.my` (wasm32, another lane's) load as before. A copy's text isn't the one the tools carry the parse of (`cached` compares a module's text with its own file's), so it is parsed where it is loaded, as a native build for Windows already does: `myla.exe check` of a program importing std.path and std.platform under Wine, 21 runs each, 29 to 38 ms (least) for both BASE's and this branch's `myla.exe`, within the noise.

**Tests.** [[tests/burn/test_windows.py]]'s `HostModules` builds `myla.exe` and `myla-lsp.exe` for Windows and runs them under Wine: `run` of a program printing `path.parent("a\\b")`, `std.platform.TARGET` and `std.path_style.WINDOWS`; `test` of its case; `check` of a program calling `platform.windows_start`, which only Windows' std.platform declares; `repl`; the language server's diagnostics of that program, from a Windows client program of the test's own (`LSP_CLIENT`: the server waits for its input to pause before it checks, which a Linux parent's pipe never shows under Wine, MYLA-708); and `myla.exe test lib/std/path.my` giving path.my's own 96 cases, as Linux's `myla` does. [[scripts/windows-runner.py]]'s `tools/myla-host-modules` runs `run` and `test` on Windows itself.

**Docs.** [[Architecture/Module-loader#copies-for-a-target]], [[Development/Testing]], the `myla` skill's compiler reference (both copies).

## Evidence

- **Test first.** `tests.burn.test_windows.HostModules` with the tests and BASE's code (`478d656`): 5 of 6 failed: `run` gave `("\nx86_64-linux\nfalse\n")` (wanted `a`, `x86_64-windows`, `true`), `test` `FAIL  up #1: expected Option.Some('a'), got Option.Some('')`, `check` `module 'std.platform' does not export 'windows_start'`, `repl` `Some("")`, the language server that error as its diagnostic; `test_a_module_of_the_library_named_is_itself` passed (the guard). After: 7 of 7 (with [[MYLA-729]]'s) pass.
- The reproduction of the task under Wine: BASE's `myla.exe run p.my` printed an empty line and `x86_64-linux`; this branch's `a` and `x86_64-windows`.
- `python3 -m unittest tests.burn.test_windows tests.burn.test_windows_runner`: 57 tests, OK (1 skipped: `WindowsTools` without `MYLA_REQUIRE_TARGETS`).
- `scripts/windows-runner.py build`: 108 of 108 programs, 162 cases; `run --wine --runs 3`: 149 passed, 0 failed, 13 skipped (the eleven console cases, `stdin/ready` and `tools/myla-build`, Windows only), `tools/myla-host-modules` among the passed.
- `build/myla test selfhost/loader.my --only same_file`: 3/3.
- The checks shared with [[MYLA-729]] and [[MYLA-734]] (the bootstrap, `check-seed.sh`, `test.sh fast`, the other targets' assembly) are in [[MYLA-734]]'s evidence.
