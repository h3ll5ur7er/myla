---
id: MYLA-734
title: "A line read from Windows' console ends with a CR"
type: bug
status: review
priority: medium
labels: [platforms, windows]
---
Found with [[MYLA-707]]. Windows' console, in its cooked mode (line input on, every program's input until it asks for raw mode), ends a line it reads with CR LF, and std.platform's `read` gives the bytes as they are, so `read_line` on a program's standard input gives `"hello\r"` on Windows where Linux gives `"hello"`: a program that compares what was typed (`if line == "y"`) works on Linux and not on Windows. A pipe or a file gives what was written, so only the console is concerned.

Reproduction, under Wine with a pseudo-terminal as the input (as [[tests/burn/test_windows.py]]'s `Console` runs it):

```myla fragment
import std.io as io

fun main() {
    var input = io.stdin()
    match input.read_line() {
        Ok(Some(line)) => print(f"{line.len()}")
        _ => print("none")
    }
}
```

Typed `hello` and Enter, it prints `6` on Windows (`5` on Linux). `Console.test_raw_mode_and_back` and `test_a_read_of_the_console_while_a_listener_takes_a_ctrl_c` pin the `\r` for now.

- [x] Decide where the CR goes: std.platform's `read` of a console handle in line-input mode giving `\n` for the console's CR LF (Python's text mode gives `\n`; Rust's `read_line` keeps the CR LF), or `read_line` dropping a `\r` before the `\n` on every target (it is documented to keep one, for files with CR LF) — the first, built; the owner decides (proposal below)
- [x] The tests above changed to expect the line without it

## What changed

**std.platform's `read` on Windows** ([[lib/std/platform_windows.my]]): after a read that succeeded, the read's last two bytes are looked at (`console_line_end`): a read ending with CR LF, or with a CR that filled it, is asked whether its handle is a console reading lines (`cooked_line`: `ENABLE_LINE_INPUT` and `ENABLE_PROCESSED_INPUT`, every program's input until it asks for raw mode). Then the CR LF is the LF (the read gives one byte fewer), and a CR that filled the read is dropped, its LF the next read's; a read of one byte that was that CR reads again, for the LF. The console gives at most one line a read (conhost keeps the rest of a pasted text for the next), so only a read's end can hold the line's end. A file's or a pipe's bytes stay as written (D215), and a read that ends otherwise costs no console call: `GetConsoleMode` is asked only after such an ending. MYLA-707's Ctrl-C retry (`console_read_aborted`, before the error is looked at) is as it was; the new code is after it, on a read that gave bytes. Nothing is kept between reads, so two workers reading the console at once share nothing new.

A key at a time (`cbreak_mode`) and raw mode clear line input, so their Enter stays a CR, as std.term reads it (`Key.Enter`). On Linux `cbreak_mode` keeps `ICRNL`, so a line read there in that mode ends with LF; on Windows with CR: a difference this leaves ([[MYLA-760]]).

**Tests.** [[tests/burn/test_windows.py]]'s `Console`: `test_raw_mode_and_back` and `test_a_read_of_the_console_while_a_listener_takes_a_ctrl_c` expect `line hello`; `test_a_line_of_the_console_read_in_pieces` (new, `CONSOLE`'s `pieces`) reads three typed lines with reads of at most 1, 3 and 64 bytes and shows each read: `[h][e][l][l][o][\n]`, `[hel][lo][\n]`, `[hello\n]`. `RUNNER_CASES` for Windows' own console ([[MYLA-708]]): the cooked lines of `terminal/01`, `02` and `06` without the CR, and `terminal/11-pieces` (new), `pieces` typed into a classic console with `WriteConsoleInputW`, which only Windows shows. `console_line_end`'s 8 and `cooked_line`'s 6 `#test` cases (pure, on every host).

**Docs.** [[Language/Targets]] (the text and the console's port), [[Language/Standard-library/Io]] (`read_line`), [[Development/Testing]].

## Proposals (accepted 2026-11-17: D246)

1. **std.platform's `read` gives a line of Windows' console with `\n`, not its CR LF** (built). The console's cooked mode is Windows' line discipline, as Linux's terminal is the one that makes Enter's CR a LF (`ICRNL`): fixing it where the console's bytes come in makes a typed line the same on both for every reader (`read_line`, `read_to_end`, a raw `read`), and leaves a file's and a pipe's bytes as written. What others do: **Rust** keeps the bytes (`stdin().read_line` gives `"hello\r\n"` on Windows' console; `BufRead::lines` drops a `\r\n` or a `\n` on every target); **Python** translates in text mode on every stream (`sys.stdin.readline()` gives `"hello\n"`, files and pipes too, universal newlines; `input()` gives `"hello"`); **Go** keeps them (`os.Stdin`'s console reader gives CR LF, `bufio.Reader.ReadString('\n')` keeps it; `bufio.Scanner`'s `ScanLines` drops a `\r` before a `\n` on every target). Alternatives: (a) `read_line` drops a `\r` before its `\n` on every target (as Go's `Scanner` and Rust's `lines`): one place, and a CR LF file reads as lines without CR, but what Linux programs read from such a file changes (`read_line` is documented to keep the CR, and its cases pin it), and a raw read or `read_to_end` of the console still gives CR LF; (b) Python's translation of every stream: against D215's same bytes; (c) keep the bytes and say so (Rust's `read_line`): `if line == "y"` works on Linux and not on Windows. Proposed row: *"A line typed at Windows' console ends with `\n`, as at a terminal on Linux ([[MYLA-734]], D215): std.platform's `read` of a console reading lines gives the CR LF that ends one as `\n` (a CR that fills a read is dropped, its LF the next read's); a file's or a pipe's bytes stay as written, and `read_line` keeps a `\r` before `\n` on every target."*

## Evidence

- **Test first.** With the tests and BASE's `lib/std/platform_windows.my`: `Console.test_raw_mode_and_back` and `test_a_read_of_the_console_while_a_listener_takes_a_ctrl_c` failed with `['line hello\r']`, `test_a_line_of_the_console_read_in_pieces` with `['1: [h][e][l][l][o][\\r][\\n]', '3: [hel][lo\\r][\\n]', '64: [hello\\r\\n]']`. After: `tests.burn.test_windows.Console`, 11 tests, OK.
- `build/myla test lib/std/platform_windows.my --stdlib lib`: 173/173 (`console_line_end` 8, `cooked_line` 6 new).
- `python3 -m unittest tests.burn.test_windows tests.burn.test_windows_runner`: 57 tests, OK (1 skipped: `WindowsTools` without `MYLA_REQUIRE_TARGETS`).
- `scripts/windows-runner.py build`: 108 of 108 programs, 162 cases; `run --wine --runs 3`: 149 passed, 0 failed, 13 skipped (the eleven console cases, `terminal/11-pieces` among them, `stdin/ready`, `tools/myla-build`: Windows only).
- Natively: `myla test lib/std/platform_windows.my --stdlib lib` with `--native` and with `--target x86_64-windows` under Wine: 173/173 each.
- **The checks of the lane** (with [[MYLA-723]] and [[MYLA-729]], at `45703f3`'s sources, 2026-11-16): the bootstrap reaches its byte-identical fixed point (29,267,619 bytes); `scripts/check-seed.sh` passes (the seeds bootstrap these sources, the embedded library is current; no `Stage:` commit: no primitive, runtime variable or attribute is new); `scripts/test.sh fast`: 1,011 tests, OK (7 skipped); `tests.burn.test_lsp`, `test_test_native`, `test_project_commands`, `test_test_functions`, `test_embedded_std`: 223 tests, OK; `.github/workflows/ci.yml` parses (11 jobs).
- **Linux, aarch64 and wasm32 unchanged**: BASE's compiler (`478d656`'s `gen_main.my`) and this branch's `stage3` write byte-identical assembly for `selfhost/gen_main.my`, `examples/maps.my` and `examples/concurrency.my` with `--target` `x86_64-linux`, `aarch64-linux` and `wasm32-wasi`, from BASE's tree and from this branch's: 18 pairs (BASE's gen_main for x86-64 29,260,935 bytes, sha256 `4a7c56029196bac2…`; this branch's 29,269,976, `3811823b84e65368…`).
