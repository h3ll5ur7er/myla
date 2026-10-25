---
id: MYLA-28
title: "Self-hosted diagnostics: shifted positions and no messages"
type: bug
status: backlog
priority: low
labels: [selfhost, diagnostics]
---
- `gen_main` and `main` report positions in amalgamated coordinates plus the 8 prelude lines: `let x: int = "s"` on line 2 is reported as `10:5`. (`check_main` parses the prelude separately, so the differential tests don't see this.)
- Lex and parse errors `panic` without a position.
- Type errors carry only a position (`CheckErr{line, col}`), no message.

## Done when

- [ ] Positions map back to the original file (see also [[MYLA-30]]: once modules aren't concatenated, each module keeps its own coordinates)
- [ ] Lexer and parser return positioned errors
- [ ] `CheckErr` carries the message text of the Python checker
