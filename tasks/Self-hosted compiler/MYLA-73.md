---
id: MYLA-73
title: Self-hosted lexer wraps integer literals of 2^63 and above
type: bug
status: review
priority: low
labels: [selfhost, lexer]
---
Found with [[MYLA-29]]. [[selfhost/lexer.my]] stores an integer literal's value as `int64`, so a literal of 2^63 or more wraps negative. The Python lexer keeps arbitrary-precision integers.

## Steps to reproduce

- `print(18446744073709551615u64)`: the Python toolchain prints `18446744073709551615`; the self-hosted checker rejects the program ("type-check failed").
- `let m = x & 9223372036854775808` in a `.my` file under `selfhost/`: `tests/burn/test_selfhost_parser.py` fails, because the canonical AST shows `(int -9223372036854775808 …)` where Python shows `(int 9223372036854775808 …)`.

Workarounds in the tree: `selfhost/floatlit.my` writes the sign bit as `(1 as uint64) << 63`, the generated float tables write bit patterns above 2^63 as negative `int64`, and the parity test `floats_in_depth` builds `2^64 - 1` as `0u64 - 1u64`.

## Done when

- [x] The lexer keeps literals up to 2^64 - 1 (for example as `uint64`, with the checker's range test and the canonical dump reading them unsigned)
- [x] The checker accepts `18446744073709551615u64` and rejects `18446744073709551616u64`, like the Python checker
- [x] A parser-parity case and a codegen case

## How

A literal is never negative (a minus is its own node), so its 64 low bits stay in the `int64` value every consumer reads, and the lexer adds the literal's decimal text when the value is 2^63 or more (`Token.big`, the fourth field of `IntLit`; computed with base-10^9 arithmetic, only for literals of 16 digits or more). The canonical token and AST dumps print that text, and the checker's range test (`lit_fits`) and its "does not fit" message use it, so literals of any size behave as in Python (a signed type still admits the magnitude 2^(w-1), as `types.int_fits` does).

Found on the way: the self-hosted **interpreter** printed, divided and compared `uint64` values above 2^63 as signed numbers; it now reads them unsigned.

The workarounds are gone: `floatlit.my` writes the sign bit as `9223372036854775808u64` (compiled by the bootstrap; the fixed point holds), and the tests use `18446744073709551615` directly. The generated float tables in `codegen.my` still write bit patterns as `int64`, which is fine: they are bit patterns, not values.

Tests: `BIG_LITERALS` in the parser and lexer gates (canonical AST and tokens: 2^63, 2^64 - 1, 2^64, hex, binary, a 39-digit literal, leading zeros), checker snippets for literals above `uint64`, `int64` and the `int32` default and a huge hex literal, and the parity program `big_integer_literals` (both native backends and the self-hosted interpreter). All failed before.
