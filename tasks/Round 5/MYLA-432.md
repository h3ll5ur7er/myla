---
id: MYLA-432
title: "P18 Check time: IoError on its own, then lazy std modules"
type: improvement
status: review
priority: medium
labels: [check-time, loader, round-5]
---
Work package P18 of [[Project/Review-2026-11-10]] (wave B). Follows D179.

- [x] `IoError` and `from_errno` in a small module of their own, so std.io and std.fs no longer import each other (std.io's import reads 36 KB instead of 81 KB; estimated 101 M to about 60 M instructions)
- [x] One list of the standard functions the back ends name (`std$fmt$…`, `std$slice$…`, `std$task$cancel`), marked as called
- [x] Then [[MYLA-413]] for the standard library (its prototype miscompiled `slices_and_formats.my` without the list)
- [ ] Then [[MYLA-412]]'s signature cache, toward [[MYLA-359]]'s 5 ms — not started: it is large (a serialized form of the seven modules' renamed declarations, every kind of declaration, type, attribute and constant expression, with node ids relocated and each module's renamer kept for its bodies, written by `scripts/bootstrap.sh` and read by the loader, with a fallback for `--stdlib`), more than this package had time for. After this package a hello world still checks in 41.3 M instructions, all of it the implicit modules' signatures, which is MYLA-412's estimate's starting point; an import now costs its modules' signatures and the bodies it calls (std.io 19 M, std.http 160 M), so the cache would pay for the other modules of `std` too

## What changed

- **std.ioerror** ([[lib/std/ioerror.my]], [[Language/Standard-library/Ioerror]]): `IoError`, `from_errno`, `io_error_name` (with `net_error`, the impl and `Format`) moved from std.fs, which re-exports the three (`pub from .ioerror import …`). std.io, std.process, std.net, std.csv, std.xml, std.http, std.compress and std.archive import it from there, so std.io, std.process, std.csv, std.xml, std.compress and std.archive no longer load std.fs.
- **`backend_std_functions`** ([[selfhost/checker.my]]): the 84 functions of `std` the lowering and the back ends call by mangled name, marked as called in `run_all`. `DeclOrigin.lazy` says whose bodies may wait (every module of `std` but the entry and std.rt); `Checker.unmarked_std` is what of those nothing called, and `CodeGen.request_fn` stops with an internal error when a back end asks for one. The interpreter running an unread body is an internal error too.
- **MYLA-413**: `Loader.lazy_std` parses every module of `std` but the entry and std.rt with its bodies left for later, and `lazy_decls` waits on `DeclOrigin.lazy`. A native build has tasks where an `async let` is in any body loaded, read or not (`LazyTable.task_line`), as before; see [[MYLA-504]].

## Proposals (open decisions)

1. **The module's name, `std.ioerror`**, and with it what a type error calls the type: `ioerror.IoError` (it said `fs.IoError`), as every message names a type by its module's last segment. Alternatives: `std.error` (`error.IoError`; a name broad enough to invite other modules' errors), or a module under `std/io/` (the message would still show its last segment). Recommended: `std.ioerror`.
2. **std.rt stays read whole.** The back ends name its functions by the primitives they replace (`myla_runtime_function`), so a lazy std.rt would need every primitive's function on the list; it is loaded only for native builds, so it costs `myla check` nothing. Its literal names are on the list anyway, so the list is whole if it is made lazy later.
3. **Tasks from an unread body** ([[MYLA-504]]): kept as before, so that generated code stays byte-identical; recommended to drop, which halves the four examples that import std.process.

## Evidence

Measurements: `myla check --stdlib lib`, callgrind's instruction count and the median wall time of 11 runs, on a machine shared with three other lanes (wall times are noisy; the instructions are exact).

| Program | Base (bb5380d) | 1. std.ioerror | 2. the list | 3. MYLA-413 |
| --- | --- | --- | --- | --- |
| hello world | 41.2 M, 13.2 ms | 41.2 M, 11.6 ms | 41.3 M, 13.3 ms | 41.3 M, 14.7 ms |
| `from std.io import println` | 112.2 M, 32.4 ms | 85.2 M, 26.1 ms | 85.3 M, 25.3 ms | 60.6 M, 17.7 ms |
| `import std.net` (`parse_ip`) | 187.4 M, 49.7 ms | 187.5 M, 53.8 ms | 188.0 M, 52.9 ms | 106.3 M, 31.1 ms |
| `import std.http` (`reason`) | 438.5 M, 124.9 ms | 438.5 M, 126.8 ms | 439.4 M, 141.4 ms | 201.1 M, 56.1 ms |

Each stage run alike (its library as `lib` in the working directory). std.net and std.http read std.fs anyway, for `read_to_string`, so item 1 doesn't change them.

`myla check selfhost/main.my`: 3,248 M → 3,106 M instructions.

Tests written first:
- `tests.burn.test_fs.IoErrorModule`: with a library whose std/fs.my doesn't parse, checking a program that imports std.io failed before (a parse error in fs.my) and passes now, and for std.process and std.csv too; the old names are the same type, interpreted and native.
- `tests.burn.test_lazy_std.BackEndNames`: the back ends' sources against the list. With `std$fmt$fmt_int` off the list it fails (`selfhost/lower.my:4883: std$fmt$fmt_int`), and the compiler built from that checker stops on examples/slices_and_formats.my: "internal error: the back end calls 'std$fmt$fmt_int', which the checker never marked as called".
- `tests.burn.test_lazy_std.ImportedStdBodies`: a broken function in std.text that nobody calls failed `myla check` before (return type mismatch at text.my:815) and passes now (check, run, build); called, directly or through another function, the error, its place and source line are the eager check's (the module's own `myla check`); the same for a parse error; a program's own module with a broken function nobody calls still fails.
- `async_let_in`'s cases in [[selfhost/loader.my]] (one in a comment or a string doesn't count) and `lazy_std`'s.

Generated code:
- Item 1, old and new library, one compiler: 38 of 42 examples byte-identical; the four that use std.io, std.fs or std.process differ only in symbols' names (`std$fs$from_errno` is `std$ioerror$from_errno`), outputs identical.
- Item 2, old and new compiler: 42 of 42 byte-identical on x86-64, aarch64 and wasm32.
- Item 3, the eager (item 2) and the lazy compiler: 42 of 42 byte-identical on x86-64, aarch64 and wasm32, outputs identical (examples/slices_and_formats.my, which the prototype miscompiled, among them). The compiler built by both: identical after `strip`; unstripped, 15 lambdas' symbol names differ by the node id in them (`interp$new_interp__lam166884` is `__lam471785`), as a lazily parsed module keeps more node ids for its bodies than its parse uses. It also builds for aarch64.
- `scripts/bootstrap.sh`: byte-identical fixed point after each item.

Suites: `scripts/test.sh fast` (843 tests; the two failures are the embedded library's, `test_embedded_std` and `test_installed`, behind `lib/` until the seed commit), `test_std_modules`, `test_compiler_parity`, `test_lsp`, `test_fs`, `test_http`, `test_stdin` (459 tests, OK), and `scripts/test.sh` at the end: 1,511 tests, the same two failures of the embedded library and no other. `myla test` of std.ioerror, fs, io, net, process, csv, xml, compress, archive and http, interpreted and `--native` (all pass), and of std.ioerror, fs, io and process on aarch64 and wasm32. `myla test` has no `--checked` (only `build` has it); its cases run checked anyway. The selfhost cases of checker, loader, codegen and interp pass (921, 141, 356, 423).

## The owner's decision (2026-11-11)

The proposals stand as built (D189).
