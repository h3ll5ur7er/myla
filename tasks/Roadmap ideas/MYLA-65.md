---
id: MYLA-65
title: Better error messages
type: improvement
status: in-progress
priority: medium
labels: [diagnostics, tooling]
---
Diagnostics that help, in both the Python and the self-hosted toolchain.

- [x] The file each error comes from ([[MYLA-10]]; the self-hosted side: [[MYLA-28]])
- [x] Spans instead of single positions, so the caret underlines the whole expression
- [ ] Notes and hints: where a binding was declared immutable, the conflicting declaration, the expected type's origin, "did you mean …" for misspelled names and fields
- [ ] More than one error per run: recover after a parse error at the next statement or declaration, keep checking other functions after a type error
- [ ] Runtime errors from native binaries with a message ([[MYLA-17]]), ideally with the source position (see [[MYLA-66]])
- [ ] The error corpus checks the new notes, so messages can't regress silently

## How

### Spans (D74)

Ranges are recorded where they are known, not measured when an error is shown: the parser is the only place that knows where a node ends.

- **Tokens** carry where they end (`Token.end_line`/`end_column`, `eline`/`ecol` in `selfhost/tokens.my`): the cursor when the scanner adds the token. `NEWLINE` and `EOF` are empty; the tokens an f-string lowers to (`format`, `(`, the format string, `,`, `)`) end after its closing quote, a hole's tokens keep their own ends shifted like their columns. The canonical token dump prints `end=line:col`, so the lexer gate compares every token's end.
- **Nodes** carry the range of the tokens the parser consumed for them: from the first to the end of the last one consumed when the node is built (`Parser._end`, `span_from`). Python: `Node.span`, set by `.at(line, col, end, start)`; self-hosted: a `sp: SrcSpan` field on `Expr`, `Stmt`, `Pattern`, `TypeExpr`, `Decl` and the records with a position (`Param`, `FieldInit`, `MatchArm`, `FunData`, `Attribute`, …, and `BindElem`'s variants). Where a node's position is not its first token, the parser captures the start before the left part (`_start()`, `mk_expr_from`): binary expressions, calls, indexing, field and tuple access, `?`, casts, pipes, assignments, expression statements, match arms, `return a, b`, and enum patterns (from `Enum` or `.`). So `f(1)` and `a + b` include their left operand, and the parentheses around an operand belong to the enclosing expression (`(1 + 2) as str`), not to the operand.
- **Errors**: `MylaError.span`, filled by `at=` a token or node: the 258 `TypeCheckError(…, X.line, X.column)` became `at=X`, the same for parse, module and runtime errors. The self-hosted `Diag`, `CheckErr`, `Report` and `RtError` carry a `SrcSpan`; `terr_at(e.line, e.col, e.sp, …)` replaces `terr(e.line, e.col, …)` where Python raises `at=e`. A lex error runs from its position to where the lexer stopped (`"oops`, `10i9`, `u{12G`); an error in an f-string hole keeps the hole's coordinates, like its position. Errors at a computed position (inside a format string) and nodes the checker synthesizes (derived `eq`, desugarings) have no range: one caret, as before.
- **Rendering** (`MylaError.caret_range`, `diag.caret_range`): the range's part on the error's line, to the end of that line when the range goes on (a declaration shows its first line), widened to the error's column, which is unchanged (`--> file:line:col` still names an operator, a call's `(`, …). Columns are code points, as before.
- The module loader keeps ranges on the nodes it rebuilds; a folded `alias.member` spans the access it replaces. The self-hosted loader positioned that node at its `.`, the Python one at the module name: it now uses the name too (`mk_expr_at`), so the `-->` line agrees.
- The REPL shifts the range to the input's lines. The language server underlines the same range instead of the word at the position (`word_end` stays for errors without a range).

Moving positions to the range's start (so `-->` points at the `nope` of `nope(1)`) is not done: it would change every position the gates and the editor tests pin, and is better decided together with notes.

### Tests

- `tests/unit/test_diagnostics.py`: the carets for lex errors (one character, a string to the end of the line, a comment's first line, a suffix, an escape), parse errors (a keyword token, an assignment target, the end of the input), type errors (an argument, a call, a method call on a chain, a cast, a pipe, parentheses, a statement, a type with arguments, a declaration spanning lines, characters beyond ASCII, an interpolation hole, a match arm); token ends; the spans themselves.
- The error corpus takes a `//~ span: <text>` directive: the text the diagnostic must underline (28 files have one).
- Gates: the lexer gate compares token ends; the lexer, parser and checker gates print errors as `err <line> <col> <span> <kind>: <message>` (`canon.canonical_error`, `diag.canonical`); the codegen gate compares the self-hosted compiler's rendered diagnostic with the Python CLI's for every lex, parse, module and type error of the corpus and for ranges that run past their line, hold characters beyond ASCII or sit in an f-string (`DIAGNOSTICS`), plus an error at a module member; the REPL tests check carets in a session.

## Evidence

Before (both CLIs) and after (both CLIs, byte for byte):

```
type error: unknown function 'nope'              type error: unknown function 'nope'
  --> type_unknown_function.my:4:17                --> type_unknown_function.my:4:17
  |                                                |
4 |     let x = nope(1)                          4 |     let x = nope(1)
  |                 ^                              |             ^^^^^^^

type error: function 'add' expects 2 …           type error: function 'add' expects 2 …
7 |     print(add(1))                            7 |     print(add(1))
  |              ^                                 |           ^^^^^^

type error: function 'f' may finish …            type error: function 'f' may finish …
4 | fun f(n: int) -> int {                       4 | fun f(n: int) -> int {
  | ^                                              | ^^^^^^^^^^^^^^^^^^^^^^

lex error: unterminated string literal           lex error: unterminated string literal
5 |     let s = "oops                            5 |     let s = "oops
  |             ^                                  |             ^^^^^

module error: cannot resolve import …            module error: cannot resolve import …
4 | import nowhere.thing                         4 | import nowhere.thing
  |        ^                                       |        ^^^^^^^^^^^^^
```

- New tests failing first: 21 of the 24 unit tests in `test_diagnostics.py` (the 3 others passed already: one caret for `$`, at the end of the input, and without a span); the self-hosted compiler built before the change printed one caret for every corpus file, and `-->` at the `.` of `lib.N` (3:17 instead of 3:14).
- Unit 479 → 503, integration 2 → 2, burn 544 → 545 (5 skipped, as before): all pass.
- Bootstrap fixed point: 7,964,179 bytes (7,876,416 before).
- Cost, the stage 3 compiler compiling the same (old) compiler source, best of 5: 1.82 s / 78 MB → 2.01 s / 93 MB (the ranges make every node 16 bytes larger, and nodes sit inline in their parents); the Python `myla check selfhost/gen_main.my`: 1.72 s → 1.88 s.
