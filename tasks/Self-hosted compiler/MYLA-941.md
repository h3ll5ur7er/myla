---
id: MYLA-941
title: "A diagnostic at the end of a CRLF line takes its `\\r` for a character: one column more, and the `\\r` in the quoted line"
type: bug
status: todo
priority: low
labels: [lexer, diagnostics, windows]
---
Found by [[MYLA-926]] step 2's port of the burn suites (2026-11-24, group D, run 277). A source file with CRLF line ends, as text-mode files and Git's `core.autocrlf` give them on Windows, gets diagnostics one column off wherever the range reaches the end of a line: the lexer counts the `\r` as a character of the line. On Linux, with the same file in LF and in CRLF:

```
$ printf 'fun main() {\r\n    let s = "abc\r\n}\r\n' > crlf.my
$ build/myla check crlf.my
2 |     let s = "abc
  |             ^^^^^
```

where the LF file gets `^^^^`.

`parse_main` says `err 2 13 2:13-2:18 lex: unterminated string literal` for it (the LF file's `2:13-2:17`); an unterminated f-string, an unterminated `{` in one and a string in its hole (`2:20` for `2:19`) are the same, and `/* not` on the last line underlines 7 for 6. The quoted line ends with the `\r` too (`3 | /* not\r`).

test_selfhost_parser's `test_syntax_errors_match_the_oracle` met this because it wrote its sources in text mode (now `newline=""`, as their recordings are LF). test_selfhost_codegen's three caret-length failures in run 277 (`/* not`, `let s = "ü`, `impl T for P {`, each one `^` longer) look like the same thing, where a checked-out file has CRLF.

Decide whether a `\r` before a `\n` is part of the line for a diagnostic (Rust's and Python's tools: no), then:

- [ ] The lexer's and the report's ranges and quoted lines without the `\r` of a CRLF line end, with `#test`s of CRLF sources
- [ ] Evidence: the CRLF and LF files above give the same diagnostics; the bootstrap's fixed point; test_selfhost_parser, test_selfhost_codegen and test_error_corpus pass
