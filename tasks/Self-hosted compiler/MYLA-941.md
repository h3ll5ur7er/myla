---
id: MYLA-941
title: "A diagnostic at the end of a CRLF line takes its `\\r` for a character: one column more, and the `\\r` in the quoted line"
type: bug
status: review
priority: low
labels: [lexer, diagnostics, windows]
---
Found by [[MYLA-926]] step 2's port of the burn suites (2026-11-24, groups D and A, run 277). A source file with CRLF line ends, as text-mode files and Git's `core.autocrlf` give them on Windows and as a Windows editor writes them, gets diagnostics one column off wherever the range reaches the end of a line, and the quoted line ends with the `\r`. On Linux, with the same file in LF and in CRLF:

```
$ printf 'fun main() {\r\n    let s = "abc\r\n}\r\n' > crlf.my
$ build/myla check crlf.my
2 |     let s = "abc
  |             ^^^^^
```

where the LF file gets `^^^^`. `parse_main` says `err 2 13 2:13-2:18 lex: unterminated string literal` for it (the LF file's `2:13-2:17`); an unterminated f-string, an unterminated `{` in one and a string in its hole (`2:20` for `2:19`) are the same, and `/* not` on the last line underlines 7 for 6.

Run 277 showed it in test_selfhost_parser's `test_syntax_errors_match_the_oracle` (group D: its sources now written with `newline=""`, as their recordings are LF), test_selfhost_codegen's diagnostics (`/* not`, `let s = "ü`, `impl T for P {`, each one `^` longer) and test_project's manifest errors (`2 | name = "1app"\r`, all four of them), which go through the same renderer.

Decided: a `\r` before a `\n` is no character of the line for a diagnostic (Rust's and Python's tools agree).

- [x] [[selfhost/diag.my]]: `shown_line` shows a line without the `\r` of its `\r\n` and stops a range that takes it in at the line's end; a line without one is shown as before (`#test`s). The line `source_line` gives kept the `\r`, and `caret_range` underlines a range that goes on to the line's whole length, `\r` included
- [x] [[selfhost/lexer.my]]'s `Lexer.fail`: a lexer that stopped at the `\n` of a `\r\n` ends the range, and puts a column there, before the `\r` (`#test`s of `lex`: three failed before). Left as it is: an unfinished `\u{…}` at a CRLF line end names the `\r` as the invalid hex digit (`2:16-2:20`), where LF names the `\n` (`2:16-3:1`); both say what the file holds
- [x] Evidence: on Linux the CRLF and LF files above give the same diagnostics (`check`, and `parse_main`'s ranges, for each of D's cases); every one of the 364 compile-error examples (`examples/errors/*.my` but `runtime_*`) as CRLF gives exactly its LF output from `myla check` and from `parse_main` (before: `parse_main` differed for 2, and `check` quoted each line with its `\r`); `selfhost/diag.my` 30/30, `selfhost/lexer.my` 167/167; the bootstrap's fixed point; check-seed.sh; test_selfhost_codegen, test_project, test_selfhost_parser and test_error_corpus pass
- [ ] test_selfhost_codegen's and test_project's diagnostics on the `burn-windows` job
