---
id: MYLA-760
title: "A key at a time on Windows' console: Enter is a CR, where Linux gives a LF"
type: bug
status: todo
priority: low
labels: [platforms, windows]
---
Found with [[MYLA-734]]. On Linux `cbreak_mode` (std.term, a key at a time, what `myla repl` keeps while an input runs) clears only `ICANON`, so the terminal still reads Enter's CR as a LF (`ICRNL`); on Windows it is the console's input without `ENABLE_LINE_INPUT` and `ENABLE_ECHO_INPUT` (D231), whose Enter is the CR alone. [[MYLA-734]] gives a cooked read's CR LF as `\n`, but not a read in this mode, so a program that reads a line (`read_line`) while the console takes keys one at a time waits on Windows for a `\n` that doesn't come: a program the REPL runs that reads its input, for one.

Reproduction (Windows only: under Wine the pseudo-terminal's own `ICRNL` makes the CR a LF before Wine's console sees it, so it prints Linux's line there too):

```myla fragment
import std.term as term
import std.io as io

fun main() {
    let m = term.cbreak_mode()
    print("ready")
    var input = io.fd_stream(0)
    match input.read(16) {
        Ok(b) => {
            var s = ""
            for c in b { s = s + f" {c}" }
            print(s)
        }
        Err(e) => print(f"error {e}")
    }
}
```

`hi` and Enter typed after `ready`: Linux prints ` 104 105 10`; Windows' console is expected to give ` 104 105 13` (to be confirmed on [[MYLA-708]]'s runner).

- [ ] What Windows' console gives in this mode, on the runner (a case of `RUNNER_CASES`)
- [ ] If it is the CR: std.platform's `read` of the console with processed input and without line input gives a CR as `\n`, as `ICRNL` does (raw mode, which clears processed input too, keeps it: std.term's `Key.Enter`)
