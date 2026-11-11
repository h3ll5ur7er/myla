# std.term

The terminal: whether a standard stream is one, its size, raw mode, styles and colours, the escape sequences that move the cursor, keys, and a line editor ([[MYLA-350]]). Nothing here is an `ioctl` or a termios byte: those are the platform's, so a port to another system (Windows next) changes the platform layer only ([[#porting-to-another-system]]). On wasm32 nothing is a terminal, the size is `None` and raw mode is `Unsupported`.

[TOC]

## Streams and size

| Item | Meaning |
| --- | --- |
| `enum Stream { Stdin, Stdout, Stderr }` | A standard stream. `Eq`, `Hash` |
| `is_tty(s: Stream) -> bool` | Whether `s` is a terminal |
| `size() -> Option<(int, int)>` | The terminal's columns and rows: the standard output's, else the standard error's, else the input's; `None` when none is a terminal (or it doesn't know its size) |
| `size_of(s: Stream) -> Option<(int, int)>` | The columns and rows of the terminal `s` is |
| `enable_ansi(s: Stream) -> bool` | Escape sequences written to `s` interpreted from now on: the system asked to where it must be (a Windows console); false when `s` isn't a terminal |
| `colors(s: Stream) -> bool` | Whether `s` should get colours: a terminal (`enable_ansi`), `TERM` not `dumb`, `NO_COLOR` unset or empty |
| `enum TermError { NotATerminal, Unsupported, Interrupted, Other(int) }` | Why the terminal can't: not a terminal, a target without them, Ctrl-C while a line was edited, another cause. `Eq`, `message()`, `Format` (D168) |

## Raw mode and keys

`raw_mode()` puts the terminal on the standard input in raw mode: each key comes as it is typed, not echoed, Ctrl-C and Ctrl-Z as keys rather than signals, special keys as their escape sequences. Output is unchanged, so `"\n"` still starts a line. It gives a `RawMode` whose `restore()` puts the terminal back as it was; restore it with `defer`, so every way out does.

The terminal is put back however the program ends, too (D187, [[MYLA-426]]): entering raw mode registers an exit hook with the runtime (`__term_raw` keeps the mode it found), which puts that mode back on every end of the program, a return from `main`, `exit`, a panic, any other runtime error, a stack overflow or a failed task, interpreted and natively, where a `defer` doesn't run (D135). `restore()` (any `__term_set` back to that mode) removes the hook. Raw mode entered again while it is on keeps the first mode, so a nested `raw_mode` and its `restore` leave the outer one's hook in place. A signal that kills the program (SIGTERM, SIGKILL) runs no hook: in raw mode Ctrl-C is a key, not SIGINT.

| Item | Meaning |
| --- | --- |
| `raw_mode() -> Result<RawMode, TermError>` | Raw mode on the input: `NotATerminal` when it isn't one |
| `RawMode`: `restore() -> Result<(), TermError>` | The mode from before `raw_mode` |
| `enum Key { Char(char), Ctrl(char), Alt(char), Enter, Tab, Backspace, Escape, Up, Down, Left, Right, Home, End, PageUp, PageDown, Insert, Delete, F(int), Unknown(str) }` | A key. `Ctrl('c')` is Ctrl-C; `Alt(c)` is ESC and a character; an arrow with a modifier is the arrow. `Eq`, `Hash` |
| `parse_key(s: str) -> Option<(Key, int)>` | The first key in the bytes `s` and how many bytes it takes; `None` when `s` is the start of one cut short (an escape sequence, a character's UTF-8) |
| `key_reader() -> KeyReader`; `KeyReader`: `next() -> Result<Option<Key>, TermError>` | The keys typed on the input, waiting for each; `None` at the input's end. A lone ESC is `Escape` once 50 ms pass without the rest of a sequence |

```myla fragment
let raw = term.raw_mode()?
defer {
    let r = raw.restore()
}
var keys = term.key_reader()
while let Ok(Some(k)) = keys.next() {
    if k == Key.Ctrl('c') || k == Key.Char('q') {
        break
    }
}
```

## Styles and colours

| Item | Meaning |
| --- | --- |
| `enum Color { Default, Black, Red, Green, Yellow, Blue, Magenta, Cyan, White, BrightBlack, …, BrightWhite, Index(int), Rgb(int, int, int) }` | The terminal's own, the 16 named ones, the 256 of the extended palette, or 24-bit. `Eq`, `Hash` |
| `style() -> Style` | The plain style |
| `Style`: `fg(c)`, `bg(c)`, `bold()`, `dim()`, `italic()`, `underline()`, `reverse()`, `strike()` | A new style with that added |
| `Style`: `sgr() -> str`, `paint(text) -> str`, `is_plain()` | Its escape sequence (SGR, `""` for the plain style); `text` between it and the reset |
| `colored(text, c)`, `reset()` | `style().fg(c).paint(text)`; the sequence back to the plain style |
| `strip(s) -> str` | `s` without its escape sequences: CSI (styles, cursor moves), OSC (titles, links), the two-byte ones |
| `width(s) -> int`, `char_width(c) -> int` | The columns a text takes, escapes left out: two for a wide (East Asian) character or an emoji, none for a combining mark or a control character |

Write styles only where `colors(stream)` says so; `paint` doesn't ask.

```myla
import std.term as term
from std.term import Color, Key, Stream

fun main() {
    let warn = term.style().fg(Color.Yellow).bold()
    let text = warn.paint("careful") + " 日本"
    print(f"{term.strip(text)}: {term.width(text)} columns, {text.len()} bytes")
    print(f"colours on stdout: {term.colors(Stream.Stdout)}")
    match term.parse_key("\u{1b}[A") {
        Some((k, n)) => print(f"{n} bytes, up: {k == Key.Up}")
        None => print("cut short")
    }
}
// output:
// careful 日本: 12 columns, 25 bytes
// colours on stdout: false
// 3 bytes, up: true
```

## The cursor and the screen

`cursor_up(n)`, `cursor_down(n)`, `cursor_right(n)`, `cursor_left(n)` (`""` for `n <= 0`), `cursor_column(col)`, `move_to(row, col)` (1, 1 the top left), `clear_screen()`, `clear_line()`, `clear_to_end()`, `hide_cursor()` and `show_cursor()` give the escape sequences; write them yourself.

## Editing a line

A `LineEdit` is a line being edited, a value with no input or output, so it is tested without a terminal. An `Editor` reads lines with it from a terminal, which is what `myla repl` does there.

| Item | Meaning |
| --- | --- |
| `line_edit(history: int) -> LineEdit` | An empty line, with a history of `history` lines behind it |
| `LineEdit`: `apply(k, history) -> EditStep`, `text()`, `render(prompt, cols) -> str` | The key applied: typing inserts at the cursor; Left, Right, Home, End (and Ctrl-B, F, A, E; Alt-B, F a word) move; Backspace, Delete, Ctrl-K (to the end), Ctrl-U (to the start), Ctrl-W (a word) delete; Up and Down (Ctrl-P, N) go through the history; Tab inserts four spaces. `render` redraws it on one row, scrolling sideways to keep the cursor in view |
| `enum EditStep { Editing, Accept, EndOfInput, Cancel }` | What the key did: Enter accepts, Ctrl-D on an empty line ends the input (else it deletes), Ctrl-C cancels |
| `editor(out: Stream) -> Editor` | An editor drawing on `out` |
| `Editor`: `read_line(prompt) -> Result<Option<str>, TermError>`, `add_history(line)` | A line read in raw mode, restored before it returns: `None` at the input's end, `Interrupted` for Ctrl-C; a line added to the history (not a blank one, nor the last again) |

## Primitives

The module rests on these ([[MYLA-350]]), each a function of `std.rt` over `std.platform`'s of the same name, and in the interpreter the host's own. Each sets `__io_errno()`, 0 on success: ENOTTY (25) for a descriptor that isn't a terminal, EBADF (9) for a negative one, ENOSYS (38) on wasm32.

| Primitive | x86-64 and aarch64 Linux | wasm32 |
| --- | --- | --- |
| `__term_is_tty(fd) -> int` | 1 when `ioctl(TCGETS)` works, else 0 | 0 |
| `__term_size(fd) -> int` | `ioctl(TIOCGWINSZ)`: the columns times 65536 plus the rows, or -1 | -1, ENOSYS |
| `__term_get(fd) -> str` | `ioctl(TCGETS)`: the kernel's `struct termios`, 36 bytes, `""` on an error | `""`, ENOSYS |
| `__term_set(fd, mode: str) -> int` | `ioctl(TCSETS)` with what `__term_get` gave; EINVAL for another size. The mode the exit hook keeps for `fd` set again removes the hook | -1, ENOSYS |
| `__term_raw(fd) -> int` | The mode now without ECHO, ICANON, ISIG, IEXTEN, ICRNL, IXON, BRKINT, INPCK, ISTRIP, with CS8, VMIN 1 and VTIME 0; OPOST kept. The mode before it is kept for the exit hook, unless the hook keeps one already (D187) | -1, ENOSYS |
| `__term_vt(fd) -> int` | 0 for a terminal (Linux's always interprets escapes), else -1 | -1, ENOSYS |

## Porting to another system

A port gives `std.platform`'s terminal functions again: `term_is_tty(fd)`, `term_size(fd)`, `term_get_mode(fd, buf)`, `term_set_mode(fd, mode)`, `term_make_raw(fd)` and `term_enable_vt(fd)`, each 0 or more or minus an errno ([[Language/Targets#the-terminal-and-signals-on-another-system]]). `std.term` and `std.rt` stay as they are. For Windows (`platform_windows.my`, over the console API):

- **Streams.** `fd` 0 to 2 are `GetStdHandle(STD_INPUT_HANDLE)`, `STD_OUTPUT_HANDLE` and `STD_ERROR_HANDLE`. `term_is_tty` is whether `GetConsoleMode` succeeds on the handle; a redirected stream is a file or a pipe and gives ENOTTY elsewhere.
- **Size.** `term_size` is `GetConsoleScreenBufferInfo`'s window, `srWindow.Right - srWindow.Left + 1` columns by `srWindow.Bottom - srWindow.Top + 1` rows (not the buffer's size), packed as `cols << 16 | rows`.
- **Mode.** `term_get_mode` writes the handle's console mode (`GetConsoleMode`, a 32-bit word) into the block, and `term_set_mode` gives it back (`SetConsoleMode`). The block is the port's own: `std.term` keeps it and hands it back unread. Raw mode is the input's, so restoring it leaves the output's escape sequences on.
- **Raw mode.** `term_make_raw` clears `ENABLE_LINE_INPUT`, `ENABLE_ECHO_INPUT` and `ENABLE_PROCESSED_INPUT` (so Ctrl-C is a key, as without ISIG) and sets `ENABLE_VIRTUAL_TERMINAL_INPUT`, so the arrows and the other special keys arrive as the same escape sequences `parse_key` decodes. The input is read as UTF-8 bytes (the console's input code page 65001, or `ReadConsoleW` converted), through `__read` as on Linux.
- **Escape sequences.** `term_enable_vt` sets `ENABLE_VIRTUAL_TERMINAL_PROCESSING` on the output handle's mode: 0 when the console accepts it, ENOTTY for a handle that isn't a console. Without it a Windows console prints the escapes, which is why `colors` asks first.
- **Errors.** `ERROR_INVALID_HANDLE` maps to EBADF (9), a handle that isn't a console to ENOTTY (25).
