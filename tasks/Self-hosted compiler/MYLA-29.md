---
id: MYLA-29
title: Self-hosted compiler has no float support
type: feature
status: backlog
priority: medium
labels: [selfhost, floats]
---
`examples/floats.my` is the only example whose self-hosted output differs: every float line is dropped, and under the self-hosted `myla run` it segfaults. The checker accepts float programs.

The root cause is in the AST, not only in codegen: `FloatLit(Option<str>)` keeps the suffix but not the digits ([[selfhost/ast.my]]), so neither codegen nor [[selfhost/interp.my]] (which evaluates every float literal to `0.0`) can know the value.

## Done when

- [ ] `FloatLit` carries the literal's value (the lexeme, or the f64 bits)
- [ ] Codegen ports the Python float path: SSE2 arithmetic and comparisons, `as` conversions, `float32` rounding, `__fmod`, `__float_to_str` with the same power-of-ten tables ([[Architecture/Native-backend]])
- [ ] `print`, `format` ([[MYLA-24]]) and the interpreter handle floats
- [ ] `examples/floats.my` matches the oracle under stage3
