---
id: MYLA-87
title: Derived Eq on an enum without payloads compares tags
type: feature
status: review
priority: medium
labels: [checker, codegen, performance, selfhost]
---
`#derive(Eq)` is lowered to a `match` over both values with one arm per variant, so `a == b` on an enum without payloads runs a chain of comparisons as long as the enum: `TokenKind` (about 70 variants) takes some 700 instructions per comparison. Profiling the language server ([[MYLA-80]]) under callgrind put 32% of a semantic-tokens request in `TokenKind.eq`, called from the self-hosted lexer and parser, which compare token kinds everywhere, so the whole self-hosted compiler pays for it (when the Python backend builds it: see How).

For an enum whose variants carry nothing, equality is the tag comparison.

- [x] Lower such a derive (both checkers) to a tag comparison, or compile `==` on it as one (both native backends and both interpreters agree on the result already)
- [x] Measure: bootstrap stage 2 time, the language server's semantic tokens for `selfhost/checker.my` (about 280 ms after MYLA-80's own optimizations), a callgrind profile
- [x] Parity tests stay green; a test that `==` on a payload-less enum is cheap (instruction count or time on a large loop)

## How

Only the Python backend needed it. The self-hosted backend already writes each derived `eq` in assembly, starting with the tag comparison (`emit_enum_eq`), so the bootstrapped compiler never paid; the slow comparisons were in the tools the Python backend builds (the language server, the test tools, stage 1).

- `types.py` marks the synthesized `eq` of an enum without payloads (`tag_eq`), and the mark follows the method into its lowered function. The body stays a `match`, for the interpreter and the checker.
- `codegen_x86.py` emits a marked function as the tag comparison: load both tags through the two argument addresses, `cmpq`, `sete`. A hand-written `impl Eq` is never marked.

## Evidence

- `tests/unit/test_compiler.py`, `TestDerivedEqOnPlainEnums`: `K.eq` for a 40-variant enum was 391 instructions and failed the test (< 15); it is 9 now. An enum with a payload keeps its match. The same check on the self-hosted backend (`test_selfhost_codegen.py`) passed before and after, which is how the difference between the backends showed.
- Parity program `derived_eq_on_plain_enums` (both backends, both interpreters, the self-hosted gates): all pairs with `==`, `!=` and a generic `T: Eq`, a struct deriving `Eq` over such an enum, a hand-written `impl Eq` on a payload-less enum that answers `true` (still called), 300,000 comparisons in a loop.
- Callgrind on `myla-lsp --resolve selfhost/checker.my`: 1,111 → 612 million instructions; `TokenKind.eq` 31% → 2.4%. Lexing is now half of it.
- Language server on `selfhost/checker.my`: semantic tokens 280 → 174 ms, a request after an edit 322 → 193 ms.
- Bootstrap stage 2 (the Python-built compiler compiling itself): 1.06 → 1.00 s, output byte-identical; compiling is dominated by the checker and code generator, not token comparisons.
