---
id: MYLA-87
title: Derived Eq on an enum without payloads compares tags
type: feature
status: backlog
priority: medium
labels: [checker, codegen, performance, selfhost]
---
`#derive(Eq)` is lowered to a `match` over both values with one arm per variant, so `a == b` on an enum without payloads runs a chain of comparisons as long as the enum: `TokenKind` (about 70 variants) takes some 700 instructions per comparison. Profiling the language server ([[MYLA-80]]) under callgrind put 32% of a semantic-tokens request in `TokenKind.eq`, called from the self-hosted lexer and parser, which compare token kinds everywhere, so the whole self-hosted compiler pays for it.

For an enum whose variants carry nothing, equality is the tag comparison.

- [ ] Lower such a derive (both checkers) to a tag comparison, or compile `==` on it as one (both native backends and both interpreters agree on the result already)
- [ ] Measure: bootstrap stage 2 time, the language server's semantic tokens for `selfhost/checker.my` (about 280 ms after MYLA-80's own optimizations), a callgrind profile
- [ ] Parity tests stay green; a test that `==` on a payload-less enum is cheap (instruction count or time on a large loop)
