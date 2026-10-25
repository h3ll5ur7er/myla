---
id: MYLA-73
title: Self-hosted lexer wraps integer literals of 2^63 and above
type: bug
status: todo
priority: low
labels: [selfhost, lexer]
---
Found with [[MYLA-29]]. [[selfhost/lexer.my]] stores an integer literal's value as `int64`, so a literal of 2^63 or more wraps negative. The Python lexer keeps arbitrary-precision integers.

## Steps to reproduce

- `print(18446744073709551615u64)`: the Python toolchain prints `18446744073709551615`; the self-hosted checker rejects the program ("type-check failed").
- `let m = x & 9223372036854775808` in a `.my` file under `selfhost/`: `tests/burn/test_selfhost_parser.py` fails, because the canonical AST shows `(int -9223372036854775808 …)` where Python shows `(int 9223372036854775808 …)`.

Workarounds in the tree: `selfhost/floatlit.my` writes the sign bit as `(1 as uint64) << 63`, the generated float tables write bit patterns above 2^63 as negative `int64`, and the parity test `floats_in_depth` builds `2^64 - 1` as `0u64 - 1u64`.

## Done when

- [ ] The lexer keeps literals up to 2^64 - 1 (for example as `uint64`, with the checker's range test and the canonical dump reading them unsigned)
- [ ] The checker accepts `18446744073709551615u64` and rejects `18446744073709551616u64`, like the Python checker
- [ ] A parser-parity case and a codegen case
