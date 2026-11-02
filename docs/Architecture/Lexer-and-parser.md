# Lexer and parser

The lexer ([[selfhost/lexer.my]], with the tokens in [[selfhost/tokens.my]]) and the parser ([[selfhost/parser.my]], with the AST in [[selfhost/ast.my]]) of the self-hosted toolchain. They were ported from the Python lexer and parser, which the gates compared them with token by token and tree by tree until those were retired ([[MYLA-219]]); the functions keep the Python ones' names, without the leading underscore.

[TOC]

## Lexer

The lexer is a hand-written single pass over the source, decoded to code points, that tracks 1-based line and column (in code points) and produces a list of `Token`s: kind, lexeme, position, value, suffix and end. The end is the position just past the token, where the scanner stopped when it added it; `NEWLINE` (positioned at the start of the next line) and `EOF` are empty. A lex error's range runs from its position to where the lexer stopped ([[MYLA-65]]).

- Newlines become `NEWLINE` tokens, collapsed so that there is never more than one in a row, none at the start and none before `EOF`.
- Keywords are looked up after scanning an identifier. `int`, `float`, `char` and friends stay `IDENT`s.
- Numbers: `scan_digits` enforces the separator rule; a decimal number becomes a `FLOAT` when it has a fraction (a `.` followed by a digit), an exponent, or an `f32`/`f64` suffix; otherwise an `INT` with an optional `iN`/`uN` suffix. Letters glued to a number are an error.
- Character literals produce a `CHAR` token whose value is the code point, which the parser turns into a char literal.
- **f-strings are lowered in the lexer** (`scan_fstring`): the literal parts become one format string, each `{…}` hole is cut out by a brace-counting scan that skips nested string and char literals (`scan_fstring_hole`), lexed again with a fresh lexer, and its tokens' columns are shifted back to their place in the source. The output is the token sequence of `format("…", hole, …)`; the tokens that aren't from a hole all start at the `f` and end after the closing quote.
- `<<` and `>>` are never produced; `|>`, `=>`, `->`, `..` and the two-character comparisons are.

## AST

The node families (`Expr`, `Stmt`, `Pattern`, `TypeExpr`, `Decl`) are wrapper structs `{id, line, col, sp, kind}`: an enum `…Kind` carries the variant's data, the wrapper a node id unique in the program (the key of the checker's side tables) and the position. `line`/`col` is where diagnostics point, `sp` the range of the tokens the parser consumed for the node, from its start (by default the position) to the end of the last token consumed when the node is built (`span_from`). Binary expressions, calls, indexing, field access, `?`, casts, pipes, assignments, expression statements, match arms and `return a, b` start where their left part began (`mk_expr_from` and friends, given the token it began with); an enum pattern starts at its enum name or `.` ([[MYLA-65]]). Type annotations are `TypeExpr`s (`TRef`, `TTuple`, `TList`, `TMap`, `TFn`); the checker turns them into `Type` values.

The AST is immutable: the checker records what it finds in side tables keyed by node id (`resolved`, the type of every expression, and others), which the interpreter and the code generator read. (The Python checker added attributes to the nodes instead.)

## Parser

The parser is recursive descent with one method per precedence level (`pipe` → `logic_or` → … → `unary` → `postfix` → `primary`). A syntax error is kept as pending (`fail`), and the parse jumps to the end of the input, where every loop ends, which unwinds it; three places record the error and resume, so a run reports up to 20 errors (`MAX_ERRORS`, D80, [[MYLA-65]]):

- **Where.** `block` around each statement, `member_recovered` around each method of an impl or trait body, `parse_program` around each declaration (`recovered`). `parse_source_all` returns every error, `parse_source` the first.
- **How far it skips** (`sync`). From the error, keeping track of the brackets opened since the statement, member or declaration began (and not closed), so a call or a `match` spanning lines is skipped whole. A statement ends at a newline or `;` with no brace open; with only parentheses or brackets open, when the next line starts a statement, a declaration or with `}` (an unclosed `(` ends at the next statement). A member or declaration ends at a line starting a declaration (`fun`, `struct`, `enum`, `impl`, `trait`, `typealias`, `const`, `import`, `from`, `pub`, `#`) with no brace open, or at column 1. A `}` that closes the enclosing block or body ends a statement or member skip.
- **Missing braces.** When the last error is at a line starting a declaration, the block or body being parsed is missing its `}`: `unwind` leaves it without a new error, and the impl or trait body (at an indented `fun`) or the program goes on there. So `if c {` without its `}` gives one error, at the next declaration, and that declaration is parsed.
- **Cascades.** An error that is not after the last one recorded is dropped, and each recovery point moves past the token it started at unless a block or body ends there, so the parser never loops.
- The Python parser did the same with an exception, `ParseError`, caught at the same three places.

Details worth knowing:

- **Statement termination.** `block` requires a `NEWLINE` or `}` after each statement; `terminate` does the same for declarations. Newlines are skipped explicitly only in lists, call arguments, attribute arguments, struct/enum bodies, struct literals and between match arms.
- **Struct literals in conditions.** `expression_ns` (no struct literals) is used for `if`/`while`/`for`/`match` heads and guards; `( … )` turns struct literals back on.
- **`else` on the next line**: after an `if` block the parser looks past newlines for `else` and backtracks when there is none.
- **Shifts** are two `<`/`>` tokens whose columns touch (`adjacent_shift`).
- **Lambdas** are recognised by `lambda_ahead`, which scans to the parenthesis matching the current `(` and checks for `=>` right after it.
- **Partial-application holes**: a `_` that is a whole call argument becomes a `Hole`; anywhere else `_` is an ordinary name and the checker rejects it.
- **Desugaring here**: `x |> f(a)` becomes the call `f(x, a)`; `return a, b` returns a tuple literal.
- **Assignment targets** are validated syntactically (`is_lvalue`: a name, or field/index chains on one).
- **Patterns** are parsed separately (`pattern`): a lone identifier becomes a binding; the checker decides later whether it is a payload-less variant.

## Canonical dumps

The self-hosting gates compare stable, implementation-independent formats: one token per line (`KIND line col "lexeme" [int=…] [suf=…] [cp=…] end=line:col`, `canonical_line` in `lexer.my`, printed by `selfhost/lex_main.my`) and one S-expression per declaration without positions (`dump_*` in `ast.my`, printed by `selfhost/parse_main.my`). An error is the line `err <line> <col> <span> <kind>: <message>`, followed by a `<label> <line> <col> <span>: <message>` line for each of its notes (D83; `canonical_err` and `canonical_note` in `diag.my`), one such line for each error of a run (D80). The formats are the ones the Python toolchain printed (`myla tokenize --canonical`, `myla parse --canonical`), and the gates compare with its recorded dumps ([[Development/Testing]]); that is how the self-hosted lexer and parser were brought up ([[Architecture/Self-hosted-compiler]]).
