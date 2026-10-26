---
id: MYLA-28
title: "Self-hosted diagnostics: shifted positions and no messages"
type: bug
status: in-progress
priority: low
labels: [selfhost, diagnostics]
---
- ~~`gen_main` and `main` report positions in amalgamated coordinates plus the 8 prelude lines~~: since [[MYLA-30]] each module keeps its own coordinates (`let x: int = "s"` on line 2 is reported as `2:5`), but a type error doesn't say which file it is in.
- ~~Lex and parse errors `panic` without a position.~~ Done: see below.
- ~~Type errors carry only a position (`CheckErr{line, col}`), no message.~~ Done: see below.

## Done when

- [ ] Type errors name their file (positions are already per file since [[MYLA-30]])
- [x] Lexer and parser return positioned errors
- [x] `CheckErr` carries the message text of the Python checker

## Lex and parse errors (done)

The lexer and parser record their first error (`Diag{kind, line, col, msg}`, [[selfhost/tokens.my]]) with the Python front end's message and position, jump to the end of the input (where every loop ends) and return it: `lex` and `parse` return `Result`, and `parse_source` does both. The loader attaches the module's path (`Report`), and [[selfhost/diag.my]] prints it as the Python CLI does (message, `--> file:line:col`, source line, caret), so `myla run` on each of the 19 lex and parse files of the error corpus prints byte for byte what the Python CLI prints. The loader's messages now use the real em dash too.

- Tests: the lexer and parser gates compare errors as well (the corpus, 49 snippets for every message, and every line prefix of six examples, 695 subtests that failed before); the codegen gate's `MODULE_ERRORS` compares the whole printed diagnostic, lex and parse errors in imported modules included.
- Found on the way: the Python backend crashed on a match that yields an aggregate when an arm ends in `panic`/`unreachable` (it tried to store the call's result); fixed in `_gen_arm_body`, with the parity program `diverging_arm_of_an_aggregate_match` (both backends).
- The four bring-up probes (`probe_*.my`) are deleted ([[MYLA-34]]).

## Type error messages (done)

Every one of the checker's 271 error sites now builds the Python checker's message (`terr(line, col, msg)`, with `type_name` writing types as types.py does); `mkerr` is gone. The port exposed two spots where the self-hosted AST lacked positions Python reports: destructuring statements are now positioned at `let`, and bindings carry their own positions (`BName`/`BTuple`, the top-level tuple held as one `BindElem`).

- Tests: the checker gate compares `err <line> <col> type: <message>` on the corpus, on 102 programs the Python unit tests expect to fail (collected by `scripts/harvest_type_errors.py` into `tests/burn/data/type_error_snippets.json`), and on 122 snippets for the messages those don't reach (`TYPE_ERRORS`). Together they reach 241 of the 252 `raise` sites in types.py (the rest are defensive or unreachable). Before: 211 of these cases differed; a mutant with one altered message fails 3.
