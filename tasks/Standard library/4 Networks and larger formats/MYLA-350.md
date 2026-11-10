---
id: MYLA-350
title: std.term and std.signal
type: feature
status: done
priority: low
labels: [stdlib, terminal, primitives, wave-4]
---
Wave 4 of [[Project/Standard-library-roadmap]], roadmap #63, #64. The platform track's third task: `ioctl` for the terminal and signal handling need primitives.

- **Owns:** `lib/std/term.my`, `lib/std/signal.my`, `lib/std/platform*.my`, `selfhost/` (primitives)
- **Needs:** [[MYLA-336]]

- [x] ANSI colours and styles; `is_tty`; the terminal's size; raw mode
- [x] SIGINT and SIGTERM as an async event a program awaits
- [x] The REPL's line editing moved onto `std.term` as the proof

## Done (2026-11-08)

Eight primitives, each a function of `std.rt` over a `std.platform` function of the same name on x86-64, aarch64 and wasm32, and the host's own in the interpreter (`is_term_primitive` in the checker; the tables are on [[Language/Standard-library/Term#primitives]] and [[Language/Standard-library/Signal#primitives]]): `__term_is_tty(fd)`, `__term_size(fd)` (columns × 65536 + rows), `__term_get(fd)` (the mode as an opaque string), `__term_set(fd, mode)`, `__term_raw(fd)`, `__term_vt(fd)`, `__signal_listen(on)` and `__signal_take(h)`. On Linux the terminal is `ioctl` on the kernel's 36-byte `struct termios` and `TIOCGWINSZ`; raw mode is `cfmakeraw`'s input and local flags with OPOST kept. Signals are a self-pipe, not a signalfd (a signalfd needs SIGINT blocked in every worker thread, and the workers start before a program asks): a new runtime routine `__on_signal` (assembly in `runtime_x86.my` and `runtime_a64.my`) writes the signal's number to the pipe in the new runtime variable `__sig_pipe`, installed with `SA_RESTART`; the reactor waits for the read end with the existing `__wait_readable`, so `std.rt`'s scheduler is unchanged. The dispositions from before the first listener come back after the last. On wasm32 nothing is a terminal and the rest is ENOSYS (`Unsupported`).

`std.term` (`lib/std/term.my`): `Stream`, `is_tty`, `size`, `size_of`, `enable_ansi`, `colors` (NO_COLOR, `TERM=dumb`), `raw_mode()` and `RawMode.restore()`, `Color` and `Style` (`style().fg(c).bold().paint(s)`, `sgr`), `colored`, `reset`, cursor and clearing sequences, `strip`, `width`, `char_width`, `Key`, `parse_key`, `key_reader()`, `LineEdit` (the pure editor: `apply`, `render`), `EditStep`, `Editor` (`read_line`, `add_history`), `TermError`. `std.signal` (`lib/std/signal.my`): `Signal`, `listen()`, `Signals.next()` (async), `try_next()`, `close()`, `interrupted()` (async), `SignalError`. What a Windows port must give is on [[Language/Standard-library/Term#porting-to-another-system]], [[Language/Standard-library/Signal#porting-to-another-system]] and [[Language/Targets#the-terminal-and-signals-on-another-system]].

The REPL: `myla repl` had no line editing; on a terminal (stdin and stderr) it now reads each line with `std.term`'s `Editor` (moves, deletes, history, Ctrl-C drops the input, Ctrl-D ends), raw only while a line is typed; from a pipe it reads plain lines as before. No seed staging: the seed compiles only `selfhost/gen_main.my`, which doesn't import `repl.my` or call a new primitive; the CLI (`main.my`, with the REPL and the interpreter) is built by stage 3, which knows them. `std.rt` and `std.platform`'s new functions use only primitives the seed knows, and `__sig_pipe` and `__on_signal` are referenced only by code the compiler never calls. `scripts/bootstrap.sh` from the unchanged seed reaches the fixed point.

## Evidence

- Test first: `tests/burn/test_term.py` written before the REPL change; `Repl.test_editing_history_and_control_keys` failed (the terminal not raw at the prompt: `10 != 0`), then passed. 14 tests: `Terminal` (is_tty, size 101×33 from TIOCSWINSZ, colours with and without NO_COLOR and TERM=dumb, pipes; raw mode turns ECHO, ICANON and ISIG off as read by tcgetattr and back on, keys: an arrow, Ctrl-C, Alt-x, F5, Delete, a lone Escape), `Signals` (SIGINT and SIGTERM awaited while a ticking task runs, one queued before the await, a `task.timeout` stopping a wait, the default back after `close`, `interrupted()` without tasks, a program that never listens, an ignored SIGINT staying ignored), `Repl` (editing, history, Home, a two-line input, Ctrl-C, Ctrl-U, Ctrl-W, Ctrl-K, Ctrl-D, the terminal restored; pipes unchanged), `Primitives`, `Warnings`, `TermOnWasm`; each program interpreted and built. Natively: 13 pass, `TermOnWasm` skipped. `scripts/test-target.py aarch64-linux test_term` (qemu): OK (skipped=1). `wasm32-wasi test_term` (Node): OK, the terminal and signal classes excused in `_targets.py` and `TermOnWasm` checking `Unsupported`.
- `build/myla test lib/std/term.my --stdlib lib`: 102/102 interpreted, `--native`, `--target aarch64-linux`, `--target wasm32-wasi`; `lib/std/signal.my` 11/11 on the same four; `platform.my` (16, also `--native`), `platform_aarch64.my` (16), `platform_wasm.my` (12), `rt.my` (16).
- `test_selfhost_cases`, `test_compiler_parity`, `test_platform_primitives`, `test_net`, `test_stdio`, `test_process`, `test_selfhost_cli`, `test_std_modules`, `test_doc_blocks`: 264 tests, OK. `test_embedded_std` OK after the bootstrap.
- `scripts/test.sh fast`: 703 tests, OK. `scripts/test-target.py aarch64-linux test_term test_platform_primitives test_stdio` and the same for `wasm32-wasi`: all pass (test_term: 13 run on aarch64; 5 on wasm32, 9 excused).
- `scripts/bootstrap.sh`: byte-identical fixed point (17,370,796 bytes) from the unchanged seed.
- Measured natively, three runs of 200 SIGINTs to a built program awaiting `next()` while a task ticks every 5 ms: from `kill` to its line on the pipe, 15 to 34 µs at best, a median of 85 to 89 µs, p95 171 to 196 µs (4-core machine shared with other lanes).

## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]], with a follow-up in [[MYLA-426]]: the line editor's drawing is cubic; a panic in raw mode leaves the terminal raw (D187).
