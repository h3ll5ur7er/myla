---
id: MYLA-932
title: "The self-hosted interpreter tool (interp_main) loads Linux's std.path_style on Windows: `fs.canonical` fails there"
type: bug
status: todo
priority: high
labels: [interpreter, loader, windows]
---
Found by [[MYLA-926]] step 2's port of the burn suites (2026-11-24, the native Windows run 275): test_fs `DirectoryParity.test_where_links_lead` passes for the self-hosted native build but fails for the self-hosted interpreter, where every `fs.canonical` line is `InvalidInput` (`t/lf -> InvalidInput`, want `t/lf -> .\t\f.txt`). The `read_link` lines agree: `__read_link` is a primitive, `canonical` is std.fs's own code.

[[selfhost/interp_main.my#L49-L87]] (`main`) builds its options with `load_options(default_stdlib_root())` and hands them straight to `load_program_opts`, without `for_host` ([[selfhost/loader.my#L438]]), which `myla run` takes through the driver's `load_for_host` ([[MYLA-723]], [[Module loader]]). So an `interp_main.exe` built for Windows interprets a program with Linux's std.path_style (`WINDOWS` false), std.path, std.platform and std.system_error. `fs.canonical` then joins the working directory `C:\…\w` and `t/lf` with `/`, and `split_root(full, false)` takes the drive letter for a `/` root: it looks up `/:\Users\…\w/t/lf`, a name with a `:` that Windows refuses (`ERROR_INVALID_NAME`, `InvalidInput`; Wine says `NotFound`).

Reproduced under Wine with `build/myla build selfhost/interp_main.my --target x86_64-windows`: a program printing `std.path_style.WINDOWS`, `fs.current_dir()` and `fs.canonical("t/f.txt")` prints `false`, `Z:\…\w`, `NotFound` in interp_main.exe, and `true`, `Z:\…\w`, `Z:\…\w\t\f.txt` built for Windows and in `main.exe run` (which goes through `for_host`).

The test is right and stays failing until this is fixed.

- [ ] interp_main loads the program with `for_host(argv[1], opts)` (as the driver's `load_for_host` does); the other tools that interpret or check a program on the host (`play_main`?) checked for the same
- [ ] Evidence: under Wine interp_main.exe prints `true` and the canonical path for the program above; test_fs `DirectoryParity` passes on the `burn-windows` job; on Linux nothing changes (the bootstrap's fixed point, test_fs, test_selfhost_cases)
