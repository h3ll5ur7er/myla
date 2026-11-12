---
id: MYLA-426
title: "P12 Terminal, paths, arguments, platform corners, small modules"
type: bug
status: done
priority: medium
labels: [std, term, glob, args, platform, round-5]
---
Work package P12 of [[Project/Review-2026-11-09]] (wave A2). Files: `lib/std/term.my`, `glob.my`, `args.my`, `bench.my`, `text.my`, `platform_wasm.my`, and the runtime's exit hook for D187 (coordinate with [[MYLA-419]] in `rt.my`).

- [x] M22: `LineEdit.render` linear in the line's length (2,000 pasted characters: 10 s) ([[MYLA-350]])
- [x] D187: raw mode is restored by a runtime exit hook on every end of the program
- [x] [[MYLA-326]]'s follow-up: `glob_in` agrees with `walk` + `matches` for a dangling link named literally and a file before `/**`
- [x] [[MYLA-333]]'s follow-ups: after `--` a command is an argument; a subcommand's error prints its own usage; a spec is validated
- [x] [[MYLA-403]]'s follow-up: `std.bench` times a closure that returns nothing (after [[MYLA-417]]'s M24)
- [x] [[MYLA-341]]'s follow-ups: `wrap` and `columns` count the same unit; `ints` returns an error on a number out of range
- [x] [[MYLA-336]]'s and [[MYLA-339]]'s follow-ups: wasm32's errno table (unknown errnos aren't EIO), its seek edge cases, `lookup("localhost")`

## What changed

- **M22** (`term.my`): `render` finds the first character shown by walking back from the cursor once, instead of trying every start from 0 and measuring the span to the cursor again each time (quadratic per draw, cubic over a paste); a character typed at the end is pushed rather than the line copied. `span_width` went.
- **D187** (the runtime): a new runtime variable `__exit_hook` (96 bytes: the terminal's descriptor plus one, then the mode to put back as a static string's cell) and std.rt's `exit_program(code)` (`__exit_program`), which runs `exit_hook` and then `std.platform`'s `exit`. On x86-64 and aarch64 every end goes through it: the end after the entry point, an async entry's end, `exit` with and without tasks, the stack overflow's report (`selfhost/runtime_x86.my`, `runtime_a64.my`, `ir_x86.my`, `ir_a64.my`, `codegen.my`), and in std.rt `panic_report` (every runtime error), `panic_report_tasks`, a failed write and "every task waits"; a closed pipe's quiet end runs the hook first. `__term_raw` keeps the mode it found, unless the hook keeps one already (raw mode entered again keeps the first); `__term_set` of that mode on that descriptor removes the hook, so `RawMode.restore()` does. wasm32 has no terminal modes and keeps its own `__exit`. The interpreter is a native program, so `myla run` and `myla repl` get the same.
- **Glob** (`glob.my`): a literal component is found with `lstat` (as `walk` lists it), so a dangling link named literally matches; a file, or a link that isn't a directory, where only `**`s follow matches (`f.txt/**` gives `f.txt`), in literal and wildcard components alike.
- **Args** (`args.my`): after `--` a command's name is a positional (or `UnexpectedPositional`); `parse_from` carries the usage line of the spec whose arguments were wrong, and `parse_or_exit` prints it (`usage: tool build [options] <file>`); `flag`, `option`, `positional`, `many` and `command` panic, naming the argument, on a name or short name declared twice, an empty name or one with a leading `-` or an `=`, a short name that isn't printed ASCII or is `-`, a required positional after an optional one, `many` with commands, a command twice.
- **Bench**: nothing to change after [[MYLA-417]]; a test function times `() => nothing()`, a block without a return and `() => ()`, and the page says so.
- **Text** (`text.my`): `wrap` counts characters (decoded as `for c in s` decodes them), the unit `columns` counts, through one `char_count`; `ints` and `longs` return `Result<[…], ScanError>`, an `Overflow` at the number's first byte (D184).
- **wasm32** (`platform_wasm.my`, `tools/wasm/`): the errno table maps all 76 of WASI preview 1's errnos onto Linux's (EPERM is now 1, not EACCES); one WASI doesn't define is 4096 plus it. A seek result past `int64`'s range is EINVAL. Node's shim names every errno, reckons the cursor in BigInts, refuses one below 0 or past 2^53 - 1 with EINVAL and leaves the cursor where it was on a failure (it lost precision, moved the cursor on a failure and gave EIO for every error it didn't name).
- **`lookup("localhost")`** (`net.my`, [[MYLA-419]]'s file, a small change): `localhost` and the names below it are `127.0.0.1` and `::1` when the hosts file has no entry for them, or there is none (wasm32), as RFC 6761 says; the hosts file still wins.

## Proposals (open decisions)

1. **`wrap`'s and `columns`' unit: characters** (Unicode scalars, as `pad_start` and format specs count). Alternatives: bytes for both (strings are bytes, but a column with `é` would misalign); terminal columns for both (`std.term.width`: wide characters count two; it would make std.text import std.term, or move `char_width` down).
2. **`ints`/`longs` return `Result<[int], ScanError>`** with `ScanErrorKind.Overflow`, the scanner's error type (D184 settles that they return an error; the type is the choice). Alternatives: an error enum of their own; keep the panicking forms and add `try_ints`.
3. **A WASI errno outside WASI preview 1's 76 is `4096 + e`**, so it reaches `IoError.Other(4096 + e)`, past every Linux errno. Alternatives: EIO as before (hides the cause); the bare WASI number (collides with Linux's).
4. **`localhost` is the loopback on every target** when the hosts file doesn't name it (RFC 6761). Alternative: `lookup` on wasm32 is `Unsupported` for any name that isn't an address, as the sockets are.
5. **The exit hook is the terminal's alone**, kept by `__term_raw` in a runtime variable, not a general `at_exit` list of closures: it allocates nothing at the end (an out-of-memory panic ends through it) and needs no call of Myla code from the end of a failed task. A general hook can be built on `exit_program` when a second user appears.
6. **A spec that can't be parsed is a panic where it is built** (a mistake in the program, as an undeclared name is). Alternative: `parse` validates and returns a new `ArgsError` variant.

Left as it is: on wasm32 a seek on a directory's descriptor is EBADF (WASI's rights), where Linux gives 0.

## Staging (D156)

- `ca34622` the compiler side: `__exit_hook`, `__exit_program` and the ends through it; std.rt's `exit_program` and `exit_hook`, which only the new code generator calls, so the old seed builds stage 1.
- `07cd9dc` **Stage:** `scripts/update-seed.sh`, the seeds and `selfhost/embedded_std.my`.
- `821f6c8` the library's use: `__term_raw`, `__term_set`, `panic_report` and the other ends of std.rt, which the seed compiles.

## Evidence

- **M22**, `bug_render_cubic.my` natively: 250 / 500 / 1,000 / 2,000 characters typed, each drawn after it: 27 / 255 / 2,186 / 17,538 ms before; 2 / 2 / 5 / 9 ms after. Interpreted after: 1,080 / 2,519 / 4,710 / 10,161 ms, linear (the interpreter's cost of a draw). New `tests.burn.test_term.LongLines` (2,000 characters under 2 s natively, the bytes drawn exact) fails before (17 s), passes after; two new `render` cases (a wide character scrolled out).
- **D187**, new `tests.burn.test_term.RawModeEnds` under a pseudo-terminal (Python's `pty`), interpreted and built: a program in raw mode that returns from `main`, calls `exit(3)`, panics, indexes out of bounds, misses a map key, overflows the stack, panics after a nested raw mode, or whose task panics: before, every one left the terminal raw (`lflag & (ECHO|ICANON|ISIG)` 0, 16 failures); after, each ends with its status and its message and the terminal cooked. One that left raw mode and went raw again behind the hook's back stays raw (the hook was removed). Passes on aarch64 (qemu); excused on wasm32 (`_targets.py`, no terminals). Exits checked by hand on x86-64 and aarch64, with and without tasks: return 0, `exit` 3, `exit` in a task 4, panic 1, a task's panic 1, stack overflow 1.
- **Glob**: `tests.burn.test_fs`'s links program, `glob_in` against `walk` + `matches` for `dangling`, `dangling/**`, `f.txt/**`, `lf/**`, `**/x.txt/**`, `**/dangling/**`: before `dangling:  false` and the like (2 failures), after all agree; `glob.my`'s `globs` gains `a.txt/**`, `**/x.my/**`, `src/*/**` and six patterns in its walk-and-match loop (failed before: `expected [a.txt], got []`).
- **Args**: `subcommands` (a command after `--`), `usage_of_error` ×6, `bad_spec` ×14 (13 panics, one valid spec); before, `usage_of_error` didn't type-check (no usage in the error). 46/46.
- **Bench**: `times_a_closure_that_returns_nothing`; 23/23.
- **Text**: `ints` ×18 and `longs` ×4 as `Result`s (two `Overflow` positions, the column in characters), `wrap` `"öö öö"` at 5 and `"日本 語"` at 3, `char_count` ×2; 143/143. The page's runnable block prints `1:7: integer out of range`.
- **wasm32**: `errno_wasm.my` under Node: `loop: Other(5)`, `long: Other(5)` before; `Other(40)`, `Other(36)` after, as natively. New `test_fs` `test_errors_keep_their_numbers` and `test_seeks_past_the_ends` (an `int64` overflowed by `Current(max)`, `End(max)`, `Current(min)`, the cursor kept after failures, a hole past the end): both fail on wasm32 before (`Other(-9223372036854775808)` for a seek, `Other(5)` for ELOOP), pass after on every runner. `platform_wasm.my`'s `errno_linux` ×11.
- **localhost**: `test_net`'s hosts program (the hosts file's entry wins; no file: `127.0.0.1 ::1`; `db.localhost`) and `NetOnWasm` (`localhost` and `db.LOCALHOST.`: `127.0.0.1 ::1`, NotFound before); `is_localhost` ×5.
- **Module cases**: `myla test lib/std/<m>.my --stdlib lib` for term 102, glob 51, args 46, bench 23, text 143: all pass interpreted, `--native`, `--target aarch64-linux` and `--target wasm32-wasi`; `platform_wasm` 19/19 interpreted and on wasm32; `net` 98/98 interpreted and native; `rt` 29/29.
- **Bootstrap**: byte-identical fixed point after the compiler commit (20,129,051 bytes, from the old seed), and after the library's use on the staged seed (20,134,340 bytes).
- **Suites**: `scripts/test.sh fast` 833 tests, 1 failure: `test_embedded_std`, expected until the integrator's seed. `scripts/test-target.py wasm32-wasi` test_net, test_fs, test_platform_primitives, test_term: pass; `aarch64-linux` test_fs, test_net, test_platform_primitives, test_term: pass. `tests.burn.test_wasm` OK, `test_doc_blocks` OK. The full `scripts/test.sh`: 1,484 tests, 336 skipped, 1 failure, the same `test_embedded_std` (`test_std_modules`, `test_compiler_parity`, `test_lsp`, `test_term`, `test_fs`, `test_net` among the passes).

## The owner's decision (2026-11-11)

The proposals stand as built (D189).

## Review 2026-11-12

Signed off in [[Project/Review-2026-11-12]], with a follow-up in [[MYLA-548]]: a failure doesn't end the program while a task blocks in a key read (the terminal stays raw), and signals leave it raw (the owner's decision 2); `std.args`' spec checks are in [[MYLA-553]]. The evidence's `args 46/46` is 43 cases today.
