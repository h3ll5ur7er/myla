---
id: MYLA-15
title: "`>=` right after generic type arguments is a parse error"
type: bug
status: review
priority: low
labels: [parser]
---
`let x: Option<int>= None` fails with `expected '>' to close type arguments, found '>='`: the lexer makes `>=` one token, and `_type_args` expects `>` ([[src/myla/parser.py#L462-L476]]). The same happens with `>>=` once compound assignment exists.

## Done when

- [x] The parser splits a `>=` (and `>>`-like sequences) when it closes type arguments, the way shifts are already recognised from adjacent tokens
- [x] Parser test; same fix in [[selfhost/parser.my]]

## How

When `type_args` finds `>=` where the closing `>` belongs, it replaces that token with an `=` one column to the right and returns, so the `>` part closes the list ([[src/myla/parser.py]], [[selfhost/parser.my]]). Nested closers already arrive as separate `>` tokens, so `Option<Result<int, str>>= x` works too. The Python parser now works on a copy of the token list, because the language server reuses the list after parsing. (`>>=` doesn't exist yet: there is no compound assignment.)

## Evidence

- `TestTypeArgumentsBeforeAssign` in [[tests/unit/test_parser.py]]: three forms parse to the same AST as with a space, `1 >= 2` is still a comparison, and the error after a split `=` is at the right place. Before: `expected '>' to close type arguments, found '>='`.
- Two `SYNTAX_ERRORS` cases in [[tests/burn/test_selfhost_parser.py]] (a split `=` with a missing value, and in a parameter list) give the same messages and positions in the self-hosted parser.

