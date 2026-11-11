# std.text

What hand-written parsers and reports need beyond `split` ([[MYLA-341]]): a `Scanner` that reads a text piece by piece, `ints`, which finds every integer in a line, and text layout: word wrap, aligned columns, `indent` and `dedent`. Strings are bytes (D164): positions count bytes, and character classes are ASCII. The module builds on [[Language/Standard-library/Num]].

```myla
import std.text as text
from std.text import Align, ScanError, ScanErrorKind

// "Sensor at x=2, y=-18: closest beacon is at x=-2, y=15"
fun sensor(line: str) -> Result<[int], ScanError> {
    var sc = text.scanner(line)
    sc.expect("Sensor at x=")?
    let x = sc.int()?
    sc.expect(", y=")?
    let y = sc.int()?
    sc.expect(": closest beacon is at x=")?
    let bx = sc.int()?
    sc.expect(", y=")?
    let by = sc.int()?
    return Ok([x, y, bx, by])
}

// "turn on 0,0 through 999,999", "toggle …" or "turn off …"
fun action(line: str) -> Result<str, ScanError> {
    var sc = text.scanner(line)
    if sc.eat("toggle") {
        return Ok("toggle")
    }
    sc.expect("turn ")?
    let what = sc.ident()?
    if what != "on" && what != "off" {
        sc.pos -= what.len()
        return Err(sc.error(ScanErrorKind.Other(f"no such action: {what}")))
    }
    return Ok(what)
}

fun show(r: Result<[int], ScanError>) {
    match r {
        Ok(v) => print(v.map((n: int) => f"{n}").join(" "))
        Err(e) => print(f"{e}")
    }
}

fun main() {
    show(sensor("Sensor at x=2, y=-18: closest beacon is at x=-2, y=15"))
    show(sensor("Sensor at x=2, y=?"))
    for line in ["toggle 0,0 through 9,9", "turn up 1,1 through 2,2"] {
        match action(line) {
            Ok(a) => print(a)
            Err(e) => print(f"{e}")
        }
    }
    for line in ["#1 @ 1,-3: 4x4 on 1518-11-01", "x=1 y=99999999999"] {
        match text.ints(line) {
            Ok(ns) => print(ns.map((n: int) => f"{n}").join(" "))
            Err(e) => print(f"{e}")
        }
    }
    for line in text.wrap("The quick brown fox jumps over the lazy dog", 16) {
        print(line)
    }
    print(text.columns([["day", "stars", "ms"], ["1", "**", "0.4"], ["25", "*", "12.0"]], [Align.Left, Align.Left, Align.Right]))
    print(text.indent(text.dedent("    fun main() {\n        print(1)\n    }"), "> "))
}
// output:
// 2 -18 -2 15
// 1:18: expected an integer
// toggle
// 1:6: no such action: up
// 1 1 -3 4 4 1518 11 1
// 1:7: integer out of range
// The quick brown
// fox jumps over
// the lazy dog
// day  stars    ms
// 1    **      0.4
// 25   *      12.0
// > fun main() {
// >     print(1)
// > }
```

[TOC]

## The scanner

`text.scanner(s)` is a `Scanner` at the start of `s`. It is a value: `var sc = text.scanner(line)`, and its reading methods take `var self`. Its field `pos` is the byte offset of what comes next. A parser may set it back to an offset it saw before, to try another way or to put an error where a word started, as `action` does above.

| Method | Result |
| --- | --- |
| `sc.at_end() -> bool` | Whether the whole text is read |
| `sc.rest() -> str` | The text not read yet |
| `sc.peek() -> Option<char>` | The next character, not read; `None` at the end |
| `sc.next() -> Option<char>` | The next character, read; `None` at the end |
| `sc.take_while(pred: (char) -> bool) -> str` | The characters from here for which `pred` holds, read |
| `sc.skip_space()` | Reads past ASCII whitespace, line ends included |
| `sc.eat(lit: str) -> bool` | Reads `lit` if it comes next; whether it did |
| `sc.expect(lit: str) -> Result<(), ScanError>` | Reads `lit`, which must come next |
| `sc.int() -> Result<int, ScanError>` | Reads a decimal `int` |
| `sc.long() -> Result<int64, ScanError>` | Reads a decimal `int64` |
| `sc.ident() -> Result<str, ScanError>` | Reads an identifier: an ASCII letter or `_`, then ASCII letters, digits and `_`s |
| `sc.error(kind: ScanErrorKind) -> ScanError` | An error of `kind` at the scanner's position, for a parser's own errors |

`peek`, `next` and `take_while` go by characters, decoded from UTF-8 as `for c in s` decodes them: a byte that isn't part of a well-formed sequence is U+FFFD, and one byte long.

`int` and `long` read an optional `-` or `+` and then digits, and stop at the first byte that isn't a digit: `"12abc"` gives 12 and leaves `abc`. No space may come between the sign and the digits, and none is skipped before the number: call `skip_space` first. `int` is Myla's `int`, an `int32`. `long` is for the larger numbers puzzles often have (`int64` is a keyword and can't name a method). The digits are `std.num`'s: `int` reads what `num.parse_int32` reads, `long` what `num.parse_int_radix(s, 10)` reads, and a number out of range is an `Overflow`, not a wrapped value.

A method that fails reads nothing: after an error, `pos` is where it was, so a parser can try something else at the same place.

## Errors

`ScanError { kind: ScanErrorKind, pos: int, line: int, col: int }` says what wasn't found and where (D168): `pos` is the byte offset, and line and column count from 1, the column in characters, as for `std.json`'s and `std.csv`'s errors. `e.message()` gives the reason in words, and the `Format` impl writes `line:col: message`, as in the example. The line and column are counted when the error is made, so reading costs nothing for them.

| `ScanErrorKind` | From | Message |
| --- | --- | --- |
| `Expected(str)` | `expect`: the literal isn't next | `expected ', '` |
| `NoInt` | `int`, `long`: no digit, after an optional sign | `expected an integer` |
| `Overflow` | `int`, `long`: out of the type's range | `integer out of range` |
| `NoIdent` | `ident`: no ASCII letter or `_` | `expected an identifier` |
| `Other(str)` | `error`: a parser's own message | the message |

## The integers in a line

| Function | Result |
| --- | --- |
| `ints(line: str) -> Result<[int], ScanError>` | Every integer in `line`, in order |
| `longs(line: str) -> Result<[int64], ScanError>` | The same as `int64`s |

Everything that isn't a digit separates numbers, so `"#1 @ 1,-3: 4x4"` gives `[1, 1, -3, 4, 4]` and `"1.5"` gives `[1, 5]`. A `-` right before a digit is a sign, unless an ASCII letter or digit comes right before it. Then it joins words or numbers, as in a range, a date or a name:

| Line | `ints` |
| --- | --- |
| `x=-3, y=12` | `[-3, 12]` |
| `x=10..-5` | `[10, -5]` |
| `5-3` | `[5, 3]` |
| `1-3 a: abc` | `[1, 3]` |
| `1518-11-01` | `[1518, 11, 1]` |
| `aaaaa-bbb-z-y-x-123[abxyz]` | `[123]` |
| `--5` | `[-5]` |

The rule reads Advent of Code's inputs right: coordinates and velocities keep their signs, and ranges, dates and room names don't make negative numbers. `+` is never part of a number, which changes nothing.

A number out of the type's range is an `Overflow` error at the number's first byte, `1:7: integer out of range`, as the scanner's `int` gives (D184: a parser of outside input returns its error; until [[MYLA-426]] it was a runtime error). `longs` reads up to `int64`'s range. A program whose input is known to fit writes `text.ints(line)?` in a function that returns a `Result` with a `ScanError`, or `text.ints(line).expect("a line of numbers")`.

## Layout

| Function | Result |
| --- | --- |
| `wrap(text: str, width: int) -> [str]` | The words of `text` in lines of at most `width` characters |
| `fill(text: str, width: int) -> str` | `wrap`'s lines joined by `\n`, without one at the end |
| `columns(rows: [[str]], align: [Align], sep: str = "  ") -> str` | The rows as lines of aligned columns, joined by `\n` without one at the end |
| `indent(text: str, prefix: str) -> str` | `text` with `prefix` before every line that holds more than whitespace |
| `dedent(text: str) -> str` | `text` without the leading whitespace its lines have in common |

`wrap` fills each line greedily. Words are the runs between ASCII whitespace, line ends included, and one space joins them, so runs of spaces and blank lines become one space. The width counts characters, as `columns`, `pad_start` and format specs do, so `"öö öö"` fits a width of 5 ([[MYLA-426]]; it counted bytes before). A word longer than the width isn't broken: it stands on a line of its own, longer than the width. A width below 1 is a runtime error. Up to the joining spaces, this is Python's `textwrap.wrap` with `break_long_words=False` and `break_on_hyphens=False`, and the comparison found the same lines for 4,000 random texts and widths.

`columns` makes each column as wide as its widest cell, counted in characters, as `pad_start` and format specs count them, so a column with `é` lines up. `sep` goes between columns. `align` holds an `Align` for each column, `Align.Left` or `Align.Right`, and a column it leaves out is aligned left. A row may have fewer cells than others: its line ends after its last cell. The last cell of a line isn't padded when it is aligned left, so no line ends in spaces.

`indent` and `dedent` follow Python's `textwrap`. Lines end at `\n`; a `\r` before it stays part of the line.

- `indent` puts `prefix` before each line that holds anything but ASCII whitespace. Empty lines and lines of only whitespace stay as they are.
- `dedent` removes the longest run of spaces and tabs that starts every line holding something else. A space and a tab differ, so `"  a\n\tb"` has no common margin. A line of only spaces and tabs is made empty and doesn't count.

The comparison with Python 3.13's `textwrap.indent` and `textwrap.dedent` found the same text for 4,000 random texts each.

## Speed

Natively, on a 10 MB text of 330,235 lines such as `p=<-3123,45> v=<7,-891002>` (1,320,940 integers), best of five runs:

| What | Time | Throughput |
| --- | --- | --- |
| `ints` over the whole text | 45 ms | 220 MB/s |
| `ints` over each line of `s.lines()` | 57 ms | 175 MB/s |
| A `Scanner` reading the four numbers of each line with `expect`, `long` and `skip_space` | 69 ms | 146 MB/s |
| `s.lines()` alone, for comparison | 29 ms | 340 MB/s |
| Python 3.13, `int` of each `re.findall` match | 505 ms | 20 MB/s |

A number of up to 9 digits (18 for `long` and `longs`) always fits, so these are added up in place. A longer one is handed to `std.num`, which knows the range exactly. Handing every number to `std.num` took `ints` 138 ms, as each needed a slice and a `Result`.
