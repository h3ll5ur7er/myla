---
id: MYLA-51
title: Language server features degrade on errors and resolve by name only
type: improvement
status: backlog
priority: low
labels: [lsp]
---
- [ ] A lex error anywhere (such as a half-typed string) turns off definition, hover, references and the outline; a parse error turns off the outline, completion symbols and local definitions. Fall back to the last good parse
- [ ] Definition and references match by name across the whole workspace, ignoring imports and scopes: in this repository `main` has 158 declarations and a local `x` 385 references; locals and parameters never resolve. Use the checker's resolution (or at least scope + imports)
- [ ] `references()` re-reads and re-lexes every `.my` file on every request
- [ ] Declaration ranges stop before the closing `}`; signatures omit type parameters, bounds and `pub`; impl entries omit `Trait for`
- [ ] Completion registers no trigger characters (no member completion after `.`), offers every known member regardless of the receiver type, and its keyword list lacks `float`, `float32`, `float64`, `char`
- [ ] Workspace roots are read once and never refreshed; `workspace/didChangeWatchedFiles` is not handled
