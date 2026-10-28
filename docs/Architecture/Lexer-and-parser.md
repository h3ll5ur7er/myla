# Lexer and parser

[TOC]

## Lexer

[[src/myla/lexer.py]] is a hand-written single pass over the source string that tracks 1-based line and column (in code points) and produces a list of `Token(kind, lexeme, line, column, value, suffix, end_line, end_column)` ([[src/myla/tokens.py]]). The end is the position just past the token, where the scanner stopped when it added it; `NEWLINE` (positioned at the start of the next line) and `EOF` are empty. A lex error's range runs from its position to where the lexer stopped ([[MYLA-65]]).

- Newlines become `NEWLINE` tokens, collapsed so that there is never more than one in a row, none at the start and none before `EOF`.
- Keywords are looked up after scanning an identifier. `int`, `float`, `char` and friends stay `IDENT`s.
- Numbers: `_scan_digits` enforces the separator rule; a decimal number becomes a `FLOAT` when it has a fraction (a `.` followed by a digit), an exponent, or an `f32`/`f64` suffix; otherwise an `INT` with an optional `iN`/`uN` suffix. Letters glued to a number are an error.
- Character literals produce a `CHAR` token whose value is the code point; the parser turns it into an `IntLit` with `is_char=True`.
- **f-strings are lowered in the lexer** (`_fstring`): the literal parts become one format string, each `{…}` hole is cut out by a brace-counting scan that skips nested string and char literals, lexed again with a fresh `Lexer`, and its tokens' columns are shifted back to their place in the source. The output is the token sequence of `format("…", hole, …)`; the tokens that aren't from a hole all start at the `f` and end after the closing quote.
- `<<` and `>>` are never produced; `|>`, `=>`, `->`, `..` and the two-character comparisons are.

## AST

[[src/myla/ast.py]] has one dataclass per construct. Source positions are plain attributes set by `.at(line, col, end, start)`, not dataclass fields, so ASTs compare structurally in tests: `line`/`column` is where diagnostics point, `span` the range of the tokens the parser consumed for the node, from `start` (by default the position) to `end`, the end of the last token consumed when the node is built (`Parser._end`). Binary expressions, calls, indexing, field access, `?`, casts, pipes, assignments, expression statements, match arms and `return a, b` start where their left part began (`Parser._start` before parsing it); an enum pattern starts at its enum name or `.` ([[MYLA-65]]). Type annotations are `TypeRef`, `TupleTypeRef`, `ListTypeRef`, `MapTypeRef` and `FnTypeRef`; the checker turns them into `types.Type` values.

The checker adds attributes to nodes as it goes (`resolved_type`, `enum_ctor`, `const_ref`, `func_ref`, `method_func`, `method_is_var_self`, `indirect_call`, `type_args`, `as_variant`, `desugared`, `captures`, `lifted_name`, …). The back ends read those.

## Parser

[[src/myla/parser.py]] is recursive descent with one method per precedence level (`_pipe` → `_logic_or` → … → `_unary` → `_postfix` → `_primary`). A syntax error raises `ParseError`; the parser catches it at three places, records it and resumes, so a run reports up to 20 errors (`MAX_ERRORS`, D80, [[MYLA-65]]):

- **Where.** `_block` around each statement, `_member` around each method of an impl or trait body, `parse_program` around each declaration. `parse` raises the first error with the others in `more`.
- **How far it skips** (`_sync`). From the error, keeping track of the brackets opened since the statement, member or declaration began (and not closed), so a call or a `match` spanning lines is skipped whole. A statement ends at a newline or `;` with no brace open; with only parentheses or brackets open, when the next line starts a statement, a declaration or with `}` (an unclosed `(` ends at the next statement). A member or declaration ends at a line starting a declaration (`fun`, `struct`, `enum`, `impl`, `trait`, `typealias`, `const`, `import`, `from`, `pub`, `#`) with no brace open, or at column 1. A `}` that closes the enclosing block or body ends a statement or member skip.
- **Missing braces.** When the last error is at a line starting a declaration, the block or body being parsed is missing its `}`: `_Unwind` leaves it without a new error, and the impl or trait body (at an indented `fun`) or the program goes on there. So `if c {` without its `}` gives one error, at the next declaration, and that declaration is parsed.
- **Cascades.** An error that is not after the last one recorded is dropped, and each recovery point moves past the token it started at unless a block or body ends there, so the parser never loops.
- The self-hosted parser does the same without exceptions: `fail` keeps the error as pending and jumps to the end of the input, and the same three places record it and go back to where it was found (`recovered`, `sync`, [[Architecture/Self-hosted-compiler]]).

Details worth knowing:

- **Statement termination.** `_block` requires a `NEWLINE` or `}` after each statement; `_terminate` does the same for declarations. Newlines are skipped explicitly only in lists, call arguments, attribute arguments, struct/enum bodies, struct literals and between match arms.
- **Struct literals in conditions.** `_expression(allow_struct_lit=False)` is used for `if`/`while`/`for`/`match` heads and guards; `( … )` turns struct literals back on.
- **`else` on the next line**: after an `if` block the parser looks past newlines for `else` and backtracks when there is none.
- **Shifts** are two `<`/`>` tokens whose columns touch (`_adjacent_shift`).
- **Lambdas** are recognised by `_lambda_ahead`, which scans to the parenthesis matching the current `(` and checks for `=>` right after it.
- **Partial-application holes**: a `_` that is a whole call argument becomes `Hole`; anywhere else `_` is an ordinary name and the checker rejects it.
- **Desugaring here**: `x |> f(a)` becomes `Call(f, [x, a])`; `return a, b` becomes a `TupleLit`.
- **Assignment targets** are validated syntactically (`_is_lvalue`: a name, or field/index chains on one).
- **Patterns** are parsed separately (`_pattern`): a lone identifier becomes `PatBinding`; the checker decides later whether it is a payload-less variant.

## Canonical dumps

`myla tokenize --canonical` and `myla parse --canonical` print stable, implementation-independent formats ([[src/myla/canon.py]]): one token per line (`KIND line col "lexeme" [int=…] [suf=…] [cp=…] end=line:col`) and one S-expression per declaration (without positions). `canon.canonical_error` is the error line the self-hosted drivers print, `err <line> <col> <span> <kind>: <message>`, followed by a `<label> <line> <col> <span>: <message>` line for each of its notes (`canon.canonical_note`, D83), and `canon.canonical_errors` that for each error of a run (D80). The self-hosted lexer and parser reproduce them byte for byte; that is how they were brought up ([[Architecture/Self-hosted-compiler]]).
