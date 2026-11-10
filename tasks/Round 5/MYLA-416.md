---
id: MYLA-416
title: "P3a Lexer and parser: lazy skipping, f-string holes, D186"
type: bug
status: todo
priority: high
labels: [lexer, parser, lazy-parsing, round-5]
---
Work package P3 of [[Project/Review-2026-11-09]], the lexer and parser half that [[Project/Review-2026-11-10]] §5 splits off (wave A1). Files: `selfhost/lexer.my`, `selfhost/parser.my`, the loader's lazy entry points. Reopens [[MYLA-373]] and [[MYLA-359]].

- [ ] Z1: a method with a missing `}` can't swallow the methods after it: fall back to eager lexing when a skipped body holds a declaration keyword at the start of a line
- [ ] Z2: `body_key` packs the place the limit tests (the `{`), not the `fun` keyword's
- [ ] Z4: a `#test(…)[…]` is skipped only where an attribute may stand
- [ ] D179: an unread body carries a marker instead of an empty block (the back-end side is [[MYLA-415]])
- [ ] The skipper's three surviving mutants get tests: an `f` before a `"` taken for an f-string, braces in an f-string hole, the `}` token's column
- [ ] `scripts/update-seed.sh` checks the seven implicit modules whole (D179)
- [ ] M1 and D186: each f-string hole parsed on its own; `a < b, c > (d)` one generic call only in a call's argument list; list, map and tuple literals read comparisons
- [ ] D186: a budget for the look-ahead (32,000 comparisons in a list: 25 s)
- [ ] M14: an imported module's `#test` case with unbalanced brackets gives the right error, at the case
