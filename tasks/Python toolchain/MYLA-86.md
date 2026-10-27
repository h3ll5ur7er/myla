---
id: MYLA-86
title: More escapes in string literals (\r, \0, \u{…})
type: feature
status: backlog
priority: low
labels: [lexer, selfhost, spec, grammar]
---
String literals know only `\n`, `\t`, `\\` and `\"` ([[Language/Lexical-structure]]); character literals also have `\r`, `\0`, `\'` and `\u{…}`. Code that speaks a protocol needs `"\r\n"`: the language server ([[MYLA-80]], `tools/lsp/protocol.my`) builds it byte by byte with `append_byte(sb, 13u8)`, and its tests can't write a carriage return in a `#test` literal (`tools/lsp/text.my` has a helper just for that).

- [ ] Decide which escapes strings and f-strings get (likely the char set: `\r`, `\0`, `\u{…}`; `\'` maybe) and record it on [[Project/Decisions]]
- [ ] Both lexers, with the same errors for bad escapes (`\u{}` out of range or a surrogate, as for chars)
- [ ] [[grammar/myla.ebnf]] (`STRING`, `FSTRING_TEXT`) and the generated tree-sitter grammar, [[Language/Lexical-structure]], [[Language/Grammar]], the `myla` skill
- [ ] Lexer gate cases and error-corpus files; then use `"\r\n"` in `tools/lsp`
