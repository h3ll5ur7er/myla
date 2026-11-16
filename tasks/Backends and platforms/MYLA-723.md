---
id: MYLA-723
title: "The interpreter, myla check and the language server load the host's own modules"
type: bug
status: todo
priority: low
labels: [platforms, windows, loader]
---
Found by [[MYLA-704]]. `for_target` ([[selfhost/loader.my]]) gives a target its own `std/platform.my` and, since MYLA-704, its own copies of other modules (`std/path_windows.my` for `std/path.my`, `std/path_style_windows.my` for `std/path_style.my`). Only a native build and a native test harness call it (`compile_asm`, `native_tests` in [[selfhost/driver.my]]); `myla run`, `myla test` interpreted, `myla check`, the REPL and the language server load `std/platform.my`, `std/path.my` and `std/path_style.my` as they are, which are Linux's.

On Linux that is right (the host is x86-64 Linux, whose `platform_file` is ""). A `myla.exe` built for Windows ([[MYLA-702]], [[MYLA-709]]) interprets a program with Windows' primitives (the CLI's own std.rt is Windows') but Linux's std.path: `path.parent("C:\\a\\b")` is `""` there, and `std.platform.TARGET` says `x86_64-linux`.

To reproduce, on Linux: `myla build --target x86_64-windows selfhost/main.my -o myla.exe`, then under Wine `myla.exe run p.my` with `p.my` printing `path.parent("a\\b").unwrap_or("none")` gives `` (Windows' rules give `a`).

- [ ] The commands that load a program for the host (`run`, interpreted `test`, `check`, `repl`, the language server) load it with `for_target(opts, host())`; a test that a program interpreted by a CLI built for Windows reads Windows' std.path
