---
id: MYLA-932
title: "The self-hosted interpreter tool (interp_main) loads Linux's std.path_style on Windows: `fs.canonical` fails there"
type: bug
status: in-progress
priority: high
labels: [interpreter, loader, windows]
---
Found by [[MYLA-926]] step 2's port of the burn suites (2026-11-24, the native Windows run 275): test_fs `DirectoryParity.test_where_links_lead` passes for the self-hosted native build but fails for the self-hosted interpreter, where every `fs.canonical` line is `InvalidInput` (`t/lf -> InvalidInput`, want `t/lf -> .\t\f.txt`). The `read_link` lines agree: `__read_link` is a primitive, `canonical` is std.fs's own code.

[[selfhost/interp_main.my#L49-L87]] (`main`) builds its options with `load_options(default_stdlib_root())` and hands them straight to `load_program_opts`, without `for_host` ([[selfhost/loader.my#L438]]), which `myla run` takes through the driver's `load_for_host` ([[MYLA-723]], [[Module loader]]). So an `interp_main.exe` built for Windows interprets a program with Linux's std.path_style (`WINDOWS` false), std.path, std.platform and std.system_error. `fs.canonical` then joins the working directory `C:\…\w` and `t/lf` with `/`, and `split_root(full, false)` takes the drive letter for a `/` root: it looks up `/:\Users\…\w/t/lf`, a name with a `:` that Windows refuses (`ERROR_INVALID_NAME`, `InvalidInput`; Wine says `NotFound`).

Reproduced under Wine with `build/myla build selfhost/interp_main.my --target x86_64-windows`: a program printing `std.path_style.WINDOWS`, `fs.current_dir()` and `fs.canonical("t/f.txt")` prints `false`, `Z:\…\w`, `NotFound` in interp_main.exe, and `true`, `Z:\…\w`, `Z:\…\w\t\f.txt` built for Windows and in `main.exe run` (which goes through `for_host`).

The test is right.

- [x] interp_main loads the program with `for_host(argv[1], opts)` (as the driver's `load_for_host` does); the other tools that interpret or check a program on the host checked for the same: the driver's loads go through `load_for_host`/`load_for_target`, the REPL's through `for_host`; `play_main` runs only as wasm (its host's library is WASI's, the default), so it stays
- [ ] Evidence: under Wine interp_main.exe now gives the canonical path (`Z:\…\w\t\f.txt`, before `NotFound`); on Linux the bootstrap's fixed point, check-seed, test_fs, test_selfhost_interp, test_platform_interface, test_stdio, test_std_modules pass. Left: test_fs `DirectoryParity` passes on the `burn-windows` job; on Linux nothing changes (the bootstrap's fixed point, test_fs, test_selfhost_cases)
