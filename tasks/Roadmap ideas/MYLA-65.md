---
id: MYLA-65
title: Better error messages
type: improvement
status: review
priority: medium
labels: [diagnostics, tooling]
---
Diagnostics that help, in both the Python and the self-hosted toolchain.

- [x] The file each error comes from ([[MYLA-10]]; the self-hosted side: [[MYLA-28]])
- [x] Spans instead of single positions, so the caret underlines the whole expression
- [x] Notes and hints: where a binding was declared immutable, the conflicting declaration, the expected type's origin, "did you mean …" for misspelled names and fields (D83)
- [x] More than one error per run: recover after a parse error at the next statement or declaration, keep checking other functions after a type error (D80; going on after a declaration-level type error: [[MYLA-110]])
- [x] Runtime errors from native binaries with a message ([[MYLA-17]]), ideally with the source position (see [[MYLA-66]]): both backends print `runtime error: <message>` and the interpreter's `  --> file:line:col`, in every build, from a static position record passed to the trap (D75); the error corpus, `tests/burn/test_native_runtime.py` and the self-hosted codegen gate check it
- [x] The error corpus checks the new notes, so messages can't regress silently

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

### More than one error per run (D80)

- **Parser** ([[src/myla/parser.py]], [[selfhost/parser.my]]): `_block` (each statement), `_member` (each method of an impl or trait body) and `parse_program` (each declaration) catch a `ParseError`, record it (`_recover`) and skip to where the next one can begin (`_sync`). The skip starts from the error, with the brackets opened since the statement, member or declaration began and not yet closed (`_nest`): a statement ends at a newline or `;` with no brace open (with only `(`/`[` open, when the next line starts a statement, a declaration or with `}`), a member or declaration at a line starting a declaration (`fun struct enum impl trait typealias const import from pub #`) with no brace open or at column 1; a `}` closing the enclosing block or body ends a statement or member skip. When the last error is at a line starting a declaration, the block (or body) being parsed lacks its `}`: `_Unwind` leaves it without another error and the parse goes on at that declaration (or, at an indented `fun`, at the next method). An error that is not after the last one recorded is dropped; a recovery point always moves past where it started unless its block ends there. At `MAX_ERRORS` (20), `_Stop` ends the parse. `parse` raises the first error with the others in `MylaError.more`.
  The self-hosted parser has no exceptions: `fail` keeps the error as pending, remembers where (`resume`) and jumps to EOF, where every loop ends, which unwinds the parse as Python's exception does; the same three places check `recovered(start, mode)` after each statement, member or declaration, which records the error, goes back to `resume` and runs the same `sync`. `unwind()` is `_Unwind` (a flag the impl body and the program clear), `stopped` is `_Stop`. `parse_source_all` returns every error, `parse_source` (the language server's symbols, the grammar sampler) the first.
- **Checker** ([[src/myla/types.py]], [[selfhost/checker.my]]): the passes up to `_fold_consts` are unchanged and their first error ends the check. Then every declaration's attributes (`_check_attributes`, split out of `_check_attributes_and_entry`), the entry point (at most one of its three errors), every function body and every method body run through `_on_its_own`, which resets what a failed check leaves behind (loop depth, lambda stack and inference, return type; the self-hosted `reset_state` also frames, type parameters, bounds) and records the first error, with its declaration's file. Self-hosted: `run_all` returns `Result<int32, [CheckErr]>`, `check_body`/`note`/`full`; `build_checker_decls` and `check_program` return every error.
- **Order and limit:** errors keep the order found, so the first is the one a single-error run reported, and the canonical first line of every gate is unchanged: attribute and entry errors, then free functions, then methods, each in declaration order (entry file first). At most 20 per run (`errors.MAX_ERRORS`, `tokens.MAX_ERRORS`).
- **Output:** `cli.report_text` (Python) and `diag.render` (a `Report` now carries `more`; `chain`, `reports`, `render_one`): each error as before, a blank line apart, then `error: aborting due to N previous errors`; one error prints exactly as before. `myla check --canonical` prints a line per error. The loader turns a module's parse errors into one report (`reports`), `loader.type_errors` the checker's (each in its declaration's file); `driver`, `gen_main`, `interp_main` and `check_main`/`parse_main` (one canonical line per error) print them all. Lex, module and runtime errors stay single.
- **Editors:** the language server publishes every error, grouped by file (only `check` in `tools/lsp/server.my` changed); the REPL reports each against the input, then the summary.

### Tests (D80)

- `tests/unit/test_multiple_errors.py` (22): parse recovery (the next statement and function, the first error unchanged, a header, a statement spanning lines, an unclosed `(`, one error per statement, a missing `}` with and without an earlier error, impl members, a struct body, the end of the input, the limit, a lex error stays single); checker recovery (every function and method, attributes first, a declaration error stays single, no state left by a failed loop, the limit, each error's module); the rendering, the CLI's stderr and `check --canonical`.
- Error corpus: `//~ errors: N` (default 1, so every existing file must still report exactly one error, which all 143 do) and `//~ next: <text>` for each later error; `parse_several_errors.my` (5 errors: statement, statement after a multi-line call, header, impl member, missing brace) and `type_several_errors.my` (4: attribute, function, function, method).
- Gates compare the whole list (`canon.canonical_errors`): the parser gate with 17 recovery snippets and four garbled copies of every example (lines broken in ten ways; 124 sources, more than 50 with several errors), the checker gate with 11 snippets (functions, attributes, entry point, `#main`s, a declaration error, state after a failed loop, lambda and `#test`, generic and method bodies, the limit), the codegen gate renders several errors in one file and in two modules exactly as the Python CLI; the language server publishes every type and parse error and errors in two files; the REPL reports two errors against the input.

### Notes and help lines (D83)

- **The error:** `MylaError.notes`, a list of `errors.Note` (`label` "note" with a place in the error's file, or "help" without one; `note(message, at)`, `hint(message)`); `render` prints each after the error's line, a note with its own `-->` and carets (`_located`, shared with the error; `caret_range` became a function). Self-hosted: `tokens.Note`, `CheckErr.notes` (`with_notes`, `note_at`), `Report.notes` (`loader.type_errors` copies them), `diag.render_one` through `located`.
- **The notes** (both checkers): `_Binding.at` / `Binding.line`, `col`, `sp` record where a variable is declared (`let`/`var`, a parameter, a lambda parameter, a destructured or match binding; not a `for` variable or a method's synthesized receiver); `_declared_at` walks an assigned place to its variable for "is declared here" (assignments and `var self` calls), `_first_declared` names the earlier binding of a redeclared name, `_collect_globals` the first of a duplicate top-level name (not the prelude's: Python marks its declarations `in_prelude`, the self-hosted checker counts them, as both put them first), and a mismatched `return` outside a lambda points at `_ret_at`/`ret_at`, the function's return type.
- **Suggestions:** `_did_you_mean`/`did_you_mean` over `_edit_distance`/`edit_distance` (optimal string alignment on UTF-8 bytes), within a third of the name's length, ties to the alphabetically first (`str_before` in Myla, which has no string `<`); the candidate lists (`_value_names`, `_callable_names`, `_type_names`, a struct's fields, a type's methods) are built the same way in both, `Key.name` and `__` names left out. Unknown names (as values and as assigned places), functions, types, struct fields (access, assignment, literals, patterns) and methods (calls and partial application) get one.
- **Output:** the canonical error line is followed by one `<label> <line> <col> <span>: <message>` line per note (`canon.canonical_note`, `diag.canonical_note`, `check_main`); the language server publishes a note as `relatedInformation` and appends a help line to the message (`diagnostic`, `text_range`); the REPL shows notes against the input like the error (`in_input`).

### Tests (D83)

- Error corpus: `//~ note: <text>`, `//~ help: <text>` and `//~ note span: <text>`; the first error's notes must be exactly the named ones, so a file without directives expects none (two existing files gained notes and say so). New files: `type_assign_to_param_field`, `type_redeclared_in_scope`, `type_return_type_note`, `type_did_you_mean_{name,field,method,function,type}`; `type_assign_to_let`, `type_duplicate_decl` and `type_var_self_immutable` name their notes.
- `tests/unit/test_diagnostics.py`: a note's rendering, a help line's, the canonical lines, which name is suggested (the closest, the alphabetically first of equally close ones, none too far or too short, no `__` primitive), and the edit distance.
- The checker gate compares notes like messages: the corpus plus 22 snippets (index, element-field and match-binding roots, a `for` variable and a receiver without a note, a lambda parameter, a destructured redeclaration, `return` in a lambda and in a generic function, suggestions of a constant, a function value, a variant, an alias, a type parameter, a primitive, struct-literal and struct-pattern fields, an assigned name, a partially applied method, a called variable, nothing close, a tie). The codegen gate's CLI comparison renders every corpus file and notes on a later error and in an imported module; `test_selfhost_cli` has a REPL session with a note and a help line; the language server scenarios check `relatedInformation` and the message, against both builds.

## Evidence

### Notes and help lines

Before, both lines ended after the carets; now:

```
type error: struct 'Rect' has no field 'widht'
  --> examples/errors/type_did_you_mean_field.my:8:12
  |
8 |     print(r.widht * r.height)
  |           ^^^^^^^
help: did you mean 'width'?

type error: return type mismatch: expected 'str', found 'int32'
  --> examples/errors/type_return_type_note.my:7:5
  |
7 |     return n * 2
  |     ^^^^^^^^^^^^
note: the return type is declared here
  --> examples/errors/type_return_type_note.my:6:22
  |
6 | fun label(n: int) -> str {
  |                      ^^^
```

- Tests failing first: the 10 new corpus cases (and two existing files, which gained notes once the checker had them and now name them), the new unit tests, the REPL session and the language server scenario (`KeyError: 'relatedInformation'`); the checker gate failed on the three duplicate-declaration cases until the self-hosted checker had that note.
- Mutation checks: the self-hosted `return` note made unconditional (fails `note_return_in_lambda`), its tie-break reversed (fails `suggest_alphabetically_first`; the gate had no tie before this check), the notes rendered without their source line (fails 5 cases of the codegen gate's CLI comparison).
- Unit 570 → 575, integration 2, burn 710 → 722 (5 skipped, as before), extension 54: all pass. Bootstrap fixed point: 5,952,875 bytes.
- Cost, the compiler built by itself compiling itself, two runs of best of 3: 1.09 and 1.05 s before, 1.04 and 1.07 s after; peak 90 → 92 MB (variables carry their position).

### More than one error per run

`examples/errors/parse_several_errors.my` and `type_several_errors.my`, before (the Python CLI at 85ade00; the self-hosted one printed the same):

```
parse error: expected variable name, found '='          type error: '#test' expects 1 argument(s), got 2
  --> parse_several_errors.my:15:9                        --> type_several_errors.my:25:1
   |                                                         |
15 |     let = 1                                          25 | #test(1, 2)[3]
   |         ^                                               | ^^^^^^^^^^^^^^
```

After, the Python CLI and `build/myla` byte for byte (`cmp`), exit status 1 for both:

```
parse error: expected variable name, found '='
  --> examples/errors/parse_several_errors.my:15:9
   |
15 |     let = 1
   |         ^

parse error: expected an expression, found ')'
  --> examples/errors/parse_several_errors.my:18:18
   |
18 |     print(total +)
   |                  ^

parse error: expected ':', found 'int'
  --> examples/errors/parse_several_errors.my:21:11
   |
21 | fun add(a int, b: int) -> int {
   |           ^^^

parse error: expected a method ('fun ...') in impl block, found 'let'
  --> examples/errors/parse_several_errors.my:26:5
   |
26 |     let y = 2
   |     ^^^

parse error: expected an expression, found 'fun'
  --> examples/errors/parse_several_errors.my:36:1
   |
36 | fun after() {
   | ^^^

error: aborting due to 5 previous errors
```

The type errors: `'#test' expects 1 argument(s), got 2` (25:1), `cannot assign value of type 'bool' to binding of type 'int32'` (20:5, `main`; its second error is not reported), `unknown name 'nope'` (27:12), `return type mismatch: expected 'str', found 'int32'` (15:9, the method), then `error: aborting due to 4 previous errors`.

- Tests first: the unit tests failed before (an import error; with the parser recovery in, the checker and CLI tests still saw one error each). The corpus test then caught a missing `}` after an earlier error going unreported (4 errors instead of 5): the parser unwound at any line starting a declaration once an error was recorded; now only when the last error is there.
- Unit 544 → 566, integration 2 → 2, burn 653 → 663 (5 skipped, as before): all pass.
- Bootstrap fixed point: 8,637,111 bytes (8,560,400 before).
- Cascades: of 46 garbled examples (three lines broken each) with a parse error, 40 report errors only on or next to a broken line; the other 6 report the error where a removed `}` becomes visible (the next `#test` line) or one error per line of a `match` whose `{` was removed.

### Spans (D74)

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
