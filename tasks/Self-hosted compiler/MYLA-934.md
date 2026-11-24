---
id: MYLA-934
title: "A file with CRLF line breaks: diagnostics show the line's '\\r' and a caret too many, and std.toml takes a CRLF in a one-line string for a control character"
type: bug
status: review
priority: medium
labels: [diagnostics, toml, windows]
---
Found by [[MYLA-926]] step 2's port of the burn suites (2026-11-24, group A): on the native Windows runner (run 277) test_project and test_selfhost_codegen write their files in Python's text mode, which gives `\r\n` on Windows, as a Windows user's editor does too. Linux did the same with such a file:

- A diagnostic showed the source line with its `\r` (`2 | name = "1app"\r`) and, where the range runs to the line's end, a caret too many: `/* not` with seven carets, `let s = "ü` with three, `impl T for P {` with fifteen. [[selfhost/diag.my]]'s `source_line` keeps everything up to the `\n`, and a range the lexer ran to the `\r` (an unterminated string) or one that goes on past the line (`caret_range` underlines the line's whole length) counted it.
- std.toml read `name = "app\r\n` as `control character in a string` at the `\r` (2:12), where `name = "app\n` is `unterminated string` at the quote (2:8): `basic_string` and `literal_string` took only `\n` for the line's end, though TOML's newline is `\n` or `\r\n` (the multi-line strings, comments and the line breaks between keys already took both).

- [x] std.toml: a one-line string ends with its line at `\n` or `\r\n` alike (`at_line_end`); a `\r` alone stays a control character. `#test` cases in `reads_strings` (two failed before: `1:7: control character in a string`)
- [x] diag.my: `shown_line` shows a line without the `\r` of its `\r\n` and stops a range that takes it in at the line's end; a line without one is shown as before. `#test` cases
- [x] test_project: `test_a_manifest_with_crlf_line_breaks` writes two manifests with `\r\n` (on Linux too) and wants the diagnostics of `\n`
- [x] Evidence: on Linux `build/myla check` of a CRLF file with an unterminated string printed `2 |     let s = "ü\r` and `^^^`, now the LF file's bytes (`^^`); every one of the 364 compile-error examples (`examples/errors/*.my` but `runtime_*`) checked as CRLF prints exactly what it prints as LF; `build/myla test lib/std/toml.my` 171/171 (169/171 with the old code), `selfhost/diag.my` 30/30; the bootstrap's fixed point; test_project, test_selfhost_codegen, test_embedded_std, test_doc_blocks and test_toml pass
- [ ] test_project's and test_selfhost_codegen's diagnostics on the `burn-windows` job
