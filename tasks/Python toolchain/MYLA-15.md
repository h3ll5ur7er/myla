---
id: MYLA-15
title: "`>=` right after generic type arguments is a parse error"
type: bug
status: backlog
priority: low
labels: [parser]
---
`let x: Option<int>= None` fails with `expected '>' to close type arguments, found '>='`: the lexer makes `>=` one token, and `_type_args` expects `>` ([[src/myla/parser.py#L462-L476]]). The same happens with `>>=` once compound assignment exists.

## Done when

- [ ] The parser splits a `>=` (and `>>`-like sequences) when it closes type arguments, the way shifts are already recognised from adjacent tokens
- [ ] Parser test; same fix in [[selfhost/parser.my]] and the Rust parser
