---
id: MYLA-28
title: "Self-hosted diagnostics: shifted positions and no messages"
type: bug
status: backlog
priority: low
labels: [selfhost, diagnostics]
---
- ~~`gen_main` and `main` report positions in amalgamated coordinates plus the 8 prelude lines~~: since [[MYLA-30]] each module keeps its own coordinates (`let x: int = "s"` on line 2 is reported as `2:5`), but a type error doesn't say which file it is in.
- Lex and parse errors `panic` without a position.
- Type errors carry only a position (`CheckErr{line, col}`), no message.

## Done when

- [ ] Type errors name their file (positions are already per file since [[MYLA-30]])
- [ ] Lexer and parser return positioned errors
- [ ] `CheckErr` carries the message text of the Python checker
