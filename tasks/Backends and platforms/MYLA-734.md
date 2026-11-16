---
id: MYLA-734
title: "A line read from Windows' console ends with a CR"
type: bug
status: todo
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

- [ ] Decide where the CR goes: std.platform's `read` of a console handle in line-input mode giving `\n` for the console's CR LF (Python's text mode gives `\n`; Rust's `read_line` keeps the CR LF), or `read_line` dropping a `\r` before the `\n` on every target (it is documented to keep one, for files with CR LF)
- [ ] The tests above changed to expect the line without it
