# std.regex

Regular expressions that match in linear time ([[MYLA-335]]), after RE2: the syntax is RE2's and Go's `regexp`'s, and a search takes time proportional to the length of the text, whatever the pattern. There are no backreferences and no lookaround, which no linear-time matcher can have.

```myla
import std.regex as regex

fun main() {
    match regex.compile("(?P<user>\\w+)@(?P<host>\\w+)\\.com") {
        Ok(re) => {
            let text = "ann@example.com, bob@test.com"
            print(re.is_match(text))
            for m in re.find_all(text) {
                print(f"{m.start}-{m.end} {m.text}")
            }
            if let Some(c) = re.captures(text) {
                print(c.text(1) + " at " + c.text(2))
            }
            print(re.replace_all(text, "${host}:$user"))
        }
        Err(e) => print(f"{e}")
    }
    match regex.compile("a(b") {
        Ok(_) => print("compiled")
        Err(e) => print(f"{e}")
    }
    if let Ok(comma) = regex.compile("\\s*,\\s*") {
        print(comma.split("a , b,c").len())
    }
}
// output:
// true
// 0-15 ann@example.com
// 17-29 bob@test.com
// ann at example
// example:ann, test:bob
// missing closing ) at 1
// 3
```

[TOC]

## Functions and types

| Item | Meaning |
| --- | --- |
| `compile(pattern: str) -> Result<Regex, RegexError>` | The pattern compiled, or why it doesn't compile |
| `escape(s: str) -> str` | `s` with every byte that means something in a pattern escaped: a pattern that matches `s` itself |
| `struct Match { start: int, end: int, text: str }` | A match: its byte offsets in the text, and its text |

The methods of `Regex`:

| Method | Result |
| --- | --- |
| `is_match(s: str) -> bool` | Whether `s` has a match |
| `find(s: str) -> Option<Match>` | The leftmost-first match |
| `find_at(s: str, start: int) -> Option<Match>` | The first match that starts at `start` or later; the text before `start` still counts for `^` and `\b` |
| `find_all(s: str) -> [Match]` | Every match, left to right, none overlapping the one before |
| `captures(s: str) -> Option<Captures>` | The groups of the leftmost-first match |
| `captures_all(s: str) -> [Captures]` | The groups of every match `find_all` finds |
| `replace(s: str, with: str) -> str` | `s` with its first match replaced by `with`, expanded (below) |
| `replace_all(s: str, with: str) -> str` | `s` with every match replaced |
| `replacen(s: str, with: str, limit: int) -> str` | `s` with its first `limit` matches replaced, every one for -1: `replace` is `replacen(s, with, 1)`, `replace_all` is `replacen(s, with, -1)` |
| `split(s: str) -> [str]` | The pieces between the matches: `n` matches give `n + 1` pieces, empty ones included, as `str.split` gives them |
| `group_count() -> int` | The number of groups, the whole match not counted |
| `as_str() -> str` | The pattern |

`searcher` and `all_slots` are the matcher's own steps (a search over the DFAs or the Pike VM; the groups' offsets of successive matches), public only because a method can't be private yet ([[MYLA-433]]); a program has no need of them.

The methods of `Captures`:

| Method | Result |
| --- | --- |
| `get(i: int) -> Option<Match>` | Group `i`'s match, `None` if it didn't take part in the match or doesn't exist; group 0 is the whole match |
| `name(n: str) -> Option<Match>` | The match of the group named `n` |
| `text(i: int) -> str` | Group `i`'s text, `""` if it didn't take part |
| `len() -> int` | The number of groups, the whole match included |

## Syntax

| Pattern | Matches |
| --- | --- |
| `a`, `\.`, `\\` | The byte itself; a `\` before any ASCII punctuation (or a space) makes it literal |
| `\t \n \r \f \v \a` | Tab, newline, carriage return, form feed, vertical tab, bell |
| `\x41`, `\x{41}`, `\101` | A byte in hexadecimal or octal (`\0` and up to three octal digits; `\1` alone would be a backreference, and is an error) |
| `.` | Any byte but `\n`; any byte with the `s` flag |
| `\C` | Any byte |
| `[abc]`, `[a-z]`, `[^a-z]` | A byte of the class, or not of it. A `]` first in a class is literal, and so is a `-` first or last |
| `\d \w \s` | `[0-9]`, `[0-9A-Za-z_]`, `[\t\n\f\r ]` (RE2's `\s`, without `\v`); `\D \W \S` the bytes outside them. They work in classes too: `[\d.]` |
| `[[:alpha:]]` | A POSIX class: `alnum`, `alpha`, `ascii`, `blank`, `cntrl`, `digit`, `graph`, `lower`, `print`, `punct`, `space`, `upper`, `xdigit`; `[[:^alpha:]]` for the bytes outside one |
| `^`, `$` | The start and the end of the text; of a line too with the `m` flag (`$` before a `\n`). Without `m`, `$` doesn't match before a final `\n`, unlike Python's |
| `\A`, `\z` | The start and the end of the text, whatever the flags |
| `\b`, `\B` | A boundary between a word byte (`\w`) and another byte or an end of the text, and a position that isn't one |
| `(re)`, `(?P<name>re)`, `(?<name>re)` | A group, numbered from 1 by its `(`; a named one, whose name is letters, digits and `_` |
| `(?:re)` | A group that isn't captured |
| `x\|y` | `x`, else `y` |
| `x*`, `x+`, `x?` | Zero or more, one or more, zero or one |
| `x{n}`, `x{n,}`, `x{n,m}` | Exactly `n`, at least `n`, from `n` to `m` (counts up to 1000). A `{` that doesn't start a count is literal: `a{,3}` |
| `x*?`, `x+?`, `x??`, `x{n,m}?` | The same, as few as possible |
| `(?i)`, `(?m)`, `(?s)`, `(?U)` | Flags for the rest of the group: ASCII case folding, multi-line `^` and `$`, `.` matching `\n`, and lazy repetitions by default (`x*?` greedy). `(?i-s)` sets one and clears another; `(?i:re)` sets them for `re` only |

Two repetitions in a row (`a**`, `x{2}{3}`) are an error, as in Go; write `(?:a*)*`.

## Matches

A search finds the leftmost-first match, as RE2, Go, Rust and Perl do: the match that starts first, and among those starting there the one an alternative or a repetition prefers. `a|ab` finds `a` in `ab`, `a+` takes as much as it can and `a+?` as little. A group inside a repetition holds its last iteration, and one that didn't take part in the match is `None`. The cases of RE2's own search tests give the same matches and groups here (below).

`find_all` takes Go's and Rust's rule for empty matches: an empty match right after a match doesn't count, so `a*` on `baaac` finds 0-0, 1-4 and 5-5. After an empty match the next search starts a character on, a whole UTF-8 sequence. `split` gives the pieces around what `find_all` finds.

In the replacement of `replace` and `replace_all`, `$1` or `${1}` is group 1's text, `$name` or `${name}` a named group's, and `$$` a `$`. A name is the longest run of letters, digits and `_`, so `$1x` names a group `1x`; write `${1}x`. A group that doesn't exist or didn't take part gives nothing, and a `$` that starts no name stays as it is.

## Bytes and UTF-8

Strings are bytes (D164), and so are patterns:

- A class and `.` match one byte. `.` on `é`, two bytes in UTF-8, matches half of it: `a.b` doesn't match `aéb`, `a..b` does. A class can't hold a non-ASCII character (`[é]` is the error `NonAsciiInClass`), but bytes: `[\x80-\xff]+` matches runs of non-ASCII characters.
- A non-ASCII character in a pattern outside a class is the sequence of its bytes, repeated as one: `é+` matches `éé`.
- Positions are byte offsets, and a match may start or end inside a character. Its `text` keeps the bytes, as `StringBuilder.append(s, start, end)` does, where a slice `s[a:b]` would stop with an error inside a well-formed character (D174).
- Case folding, `\w`, `\b` and the POSIX classes are ASCII.

## Errors

`compile` gives one of these for a pattern that doesn't compile.

| Item | Meaning |
| --- | --- |
| `struct RegexError { kind: ErrorKind, pos: int }` | The reason, and the byte offset in the pattern of the construct at fault. `e.message()` is the reason in words, and `f"{e}"` gives `missing closing ) at 1` |
| `enum ErrorKind` | `MissingParen`, `UnexpectedParen`, `MissingBracket`, `InvalidEscape`, `InvalidClassRange`, `InvalidPosixClass`, `NonAsciiInClass`, `MissingRepeatArgument`, `InvalidNestedRepeat` (`a**`), `InvalidRepeatCount` (above 1000, or `{3,2}`), `InvalidGroup` (lookaround, `(?P=n)`), `InvalidGroupName`, `DuplicateGroupName`, `InvalidFlags`, `NestingTooDeep` (groups more than 100 deep), `TooLarge` (a program of more than 100,000 instructions, `((a{1000}){1000})`) |

## How it matches

A pattern is parsed to a tree and compiled to a Thompson NFA, a program of byte tests, splits, jumps, saves and assertions (`x{2,5}` becomes `xx(x(x(x)?)?)?`, as Go expands it). Three engines run it:

- **The Pike VM** walks the text once with a list of threads in priority order, at most one per instruction, each with the positions of its groups. It finds the groups, and it is the whole search on a text of fewer than 96 bytes.
- **A forward DFA**, built lazily from the program with `.*?` in front: a state is the ordered list of threads of the Pike VM without their groups, plus the class of the byte read last (for `^`, `$` and `\b`), and its transitions are made the first time the text needs them. A match drops the threads after it, so it finds the end of the leftmost-first match. `is_match` stops at the first match it sees. An assertion is decided only on the next byte, when both sides are known; a state whose threads hold one keeps the instructions they were followed from instead, and its transition follows them again in one pass, as the Pike VM does at that position. Followed on from the assertion alone, a repetition around it (`(^|a)+`, `(\b|b)*`) could go round once more through instructions the Pike VM had already visited, and give the threads another order (MYLA-421).
- **A reverse DFA** of the reversed pattern runs back from that end and finds the start: the longest match backwards.

With both ends known, `find` is done; `captures` runs the Pike VM from the start only. The DFAs keep up to 2,000 states per search; past that the search goes on in the Pike VM. A pattern that starts with literal bytes skips to them before each search.

### Measured

Natively on the development container (4 cores of a Xeon at 2.3 GHz, shared), the best of five runs, measured by a program outside the suite (2026-11-07, `cc6687f`).

| Search | Time | Throughput |
| --- | ---: | ---: |
| A literal, `needle`, over 10 MB (at the end) | 7.4 ms | 1.35 GB/s |
| `\w+@\w+\.com` over 10 MB of words, `find_all` (29,706 matches) | 42 ms | 238 MB/s |
| The same with the Pike VM alone | 551 ms | 18 MB/s |
| `\w+@\w+\.org`, `is_match`, no match in 10 MB | 30 ms | 328 MB/s |
| The same with the Pike VM alone | 445 ms | 22 MB/s |
| 100 alternatives (`bob0@\|bob37@\|…`), `find_all` over 10 MB | 39 ms | 257 MB/s |

Compiling the 100 alternatives (867 bytes) takes 65 µs.

The pathological patterns, which a backtracking matcher takes exponential time on, in linear time:

| `a` × n, no match | `(a*)*b`, Pike VM | `(a*)*b`, DFA | `(a\|a)*b`, Pike VM | `(a\|a)*b`, DFA |
| --- | ---: | ---: | ---: | ---: |
| 10,000 | 1.1 ms | 39 µs | 1.4 ms | 39 µs |
| 100,000 | 11.7 ms | 381 µs | 13.7 ms | 368 µs |
| 1,000,000 | 115 ms | 3.7 ms | 110 ms | 3.7 ms |

## Tests

The module's cases (`myla test lib/std/regex.my`, interpreted and `--native`) are:

- RE2's `re2-search.txt`, as Go's `regexp/testdata` carries it: its leftmost-first column, 1,660 cases of pattern, text and the spans of every group. Left out are the patterns with `\p`, `\Q` or `\C` (which Go doesn't have) and the cases with text outside ASCII, where Go's characters and these bytes differ.
- About 160 cases of the rest of the syntax (POSIX classes, flags, lazy and counted repetitions, named groups, anchors), with the results Go's `regexp` gave, and cases on bytes, which Go can't give.
- Every one of them is also searched by the DFAs and the Pike VM alone, which must agree: the groups, and the whole match as `find` searches it.
- Cases on texts of 96 bytes and more, searched as a caller searches them (the DFAs first): `find`, `captures`, `is_match`, `find_all` and the Pike VM alone must agree, and Go gave the results. Among them the assertions inside a repetition of MYLA-421.
- Errors with their positions, `find_all`'s empty matches, replacements, `split`, and the pathological patterns on 10,000 bytes.

The burn test `tests/burn/test_regex.py` is a differential job against Go's `regexp` and Python's `re` (MYLA-421): random patterns of the whole syntax, nested three deep, on texts mostly of 96 bytes and more; `is_match`, `find`, `find_all` and `captures` must give the oracle's answers. Go checks all of it and skips when `go` isn't installed; Python's `re`, which backtracks, checks the patterns where no repetition can match empty. 40,000 cases against Go natively, 10,000 against Python, and a few hundred interpreted.
