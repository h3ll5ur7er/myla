---
id: MYLA-934
title: "std.toml takes the CRLF that ends an unterminated one-line string for a control character"
type: bug
status: review
priority: medium
labels: [toml, windows]
---
Found by [[MYLA-926]] step 2's port of the burn suites (2026-11-24, group A): on the native Windows runner (run 277) test_project writes its manifests in Python's text mode, which gives `\r\n` on Windows, as a Windows user's editor does too. Linux did the same with such a file: std.toml read `name = "app\r\n` as `control character in a string` at the `\r` (2:12), where `name = "app\n` is `unterminated string` at the quote (2:8). `basic_string` and `literal_string` took only `\n` for the line's end, though TOML's newline is `\n` or `\r\n` (the multi-line strings, comments and the line breaks between keys already took both).

The manifest's quoted line with its `\r` and the caret too many in the same run are [[MYLA-941]]'s.

- [x] std.toml: a one-line string ends with its line at `\n` or `\r\n` alike (`at_line_end`); a `\r` alone stays a control character. `#test` cases in `reads_strings` (the two of CRLF failed before: `1:7: control character in a string`)
- [x] test_project: `test_a_manifest_with_crlf_line_breaks` writes two manifests with `\r\n` (on Linux too) and wants the diagnostics of `\n`
- [x] Evidence: `build/myla test lib/std/toml.my` 171/171 (169/171 with the old code); the bootstrap's fixed point; test_project and test_toml pass on Linux
- [ ] test_project on the `burn-windows` job
