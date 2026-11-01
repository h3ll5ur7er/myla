---
id: MYLA-86
title: More escapes in string literals (\r, \0, \u{…})
type: feature
status: done
priority: low
labels: [lexer, selfhost, spec, grammar]
---
String literals know only `\n`, `\t`, `\\` and `\"` ([[Language/Lexical-structure]]); character literals also have `\r`, `\0`, `\'` and `\u{…}`. Code that speaks a protocol needs `"\r\n"`: the language server ([[MYLA-80]], `tools/lsp/protocol.my`) builds it byte by byte with `append_byte(sb, 13u8)`, and its tests can't write a carriage return in a `#test` literal (`tools/lsp/text.my` has a helper just for that).

- [x] Decide which escapes strings and f-strings get (likely the char set: `\r`, `\0`, `\u{…}`; `\'` maybe) and record it on [[Project/Decisions]]
- [x] Both lexers, with the same errors for bad escapes (`\u{}` out of range or a surrogate, as for chars)
- [x] [[grammar/myla.ebnf]] (`STRING`, `FSTRING_TEXT`) and the generated tree-sitter grammar, [[Language/Lexical-structure]], [[Language/Grammar]], the `myla` skill
- [x] Lexer gate cases and error-corpus files; then use `"\r\n"` in `tools/lsp`

## How

Decided with the user: strings and f-strings take exactly the char escapes, and chars gain `\"`: one set, `\n \t \r \0 \\ \" \'` and `\u{…}` (D72, with [[MYLA-84]]).

- Both lexers scan an escape in one place (`_escape` in `src/myla/lexer.py`, `scan_escape` in `selfhost/lexer.my`) for chars, strings and f-strings. The `\u{…}` errors name the literal kind (`invalid Unicode scalar U+D800 in string literal …`); the char messages are unchanged. In an f-string, `\u{7B}` is a literal brace, not a hole: it goes into the lowered `format` string doubled (`{{`), as the first version didn't, which made `f"\u{7B}{x}\u{7D}"` a type error in both toolchains (found in the self-review).
- [[grammar/myla.ebnf]], [[Language/Grammar]] (one `escape` rule for `CHAR`, `STRING`, `FSTRING_TEXT`), [[Language/Lexical-structure]], the `myla` skill, the TextMate grammar (`\u{…}` coloured whole).
- `tools/lsp/protocol.my` writes `"Content-Length: …\r\n\r\n"` in one literal; `text.my`'s helper for building a carriage return is gone (`#test("a\r\nb\rc")` instead).

## Evidence

- `tests/unit/test_lexer.py`, `TestStringEscapes` (failed before): the new escapes in strings, f-strings and chars, and the errors for `\u` without a brace, surrogates, values above `10FFFF`, an empty `\u{}` in an f-string, and an unknown escape.
- Parser-gate snippets for every `\u{…}` error in strings and f-strings (the self-hosted lexer reports Python's message at Python's position); the lexer gate's token case; error-corpus `lex_string_bad_unicode_escape.my`.
- `test_fstrings` checks the doubled brace; `examples/unicode.my` prints `{6}` from `f"\u{7B}{größe}\u{7D}"`, and `\r\n`'s length, `\0` inside a string, `\u{20AC}` in an f-string, `'\"'` and `\'` in both toolchains and backends.
