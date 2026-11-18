---
id: MYLA-825
title: "Text that starts #test in a function body of an imported module is skipped unparsed (M9)"
type: bug
status: review
priority: medium
labels: [lexer, loader, round-7]
---
Filed by [[MYLA-793]] for M9 of [[Project/Review-2026-11-17]], which asked for a task of its own: old, in an imported module of the standard library and in a program's own imported modules alike.

In a module whose `#test` cases nothing runs (every module but the entry, `skip_tests`), the lexer consumed a `#test` attribute unlexed wherever an attribute may stand: at a line's start, after `;`, `{` or `}`. That holds inside a function's body too, so a line `#test(1)[2]` there vanished, and `#test("…")[ let z = y + 1000 ]` took the statement in its brackets with it: `myla check main.my` said `ok` and the program ran without them, while `myla check` of the module itself said `parse error: expected an expression, found '#'` (against D179: a library's body read late has the error of its eager check). A lazily read body (`lex_part`) skipped them the same way.

- [x] The lexer keeps where a function's body is open (`Lexer.body`: the depth of `opens` its `{` made, which `body_ahead` tells at the `{`); no `#test` is skipped in one (`attribute_may_stand`)
- [x] `lex_part` lexes a body's `#test` (it was skipped there too)
- [x] One above a method in an `impl`, or at the top level, is still skipped
- [x] Tests: `selfhost/lexer.my`'s cases, `test_lazy_std`

## Evidence

- The review's `repro-r6/loader/attr_in_body/`: at BASE `e659342` `myla check main.my --stdlib lib` and `myla check main2.my` (its own module) say `ok`, `myla run main2.my` prints `42`. After: both are `parse error: expected an expression, found '#'` at `demo.my:5:5`, the first error of `myla check` of the module itself, and `run` fails the same way.
- `selfhost/lexer.my`'s cases (`myla test selfhost/lexer.my --stdlib lib`): 162 of 162; new `skipped_shape` cases (a body's `#test` lexed; an impl's and the top level's skipped; a struct literal's `{` in a default argument is no body) and `lex_part`'s case now has the `#` and `test` tokens.
- `tests/burn/test_lazy_std.py` `ImportedStdBodies.test_a_test_attribute_in_a_body_is_an_error` (new): an imported std module and a program's own module, `check` and `run`, the error at `attr_793.my:3:5` as the module's own check gives it; a case above a method and one at the top level are still skipped (the program prints `42`).
- Cost: a hello world's `myla check` 25,494,608 → 25,508,358 instructions (callgrind, `MYLA_THREADS=1`, +0.05 %: `body_ahead` at each top-level `{` of a module read whole).
