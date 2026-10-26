---
id: MYLA-12
title: "Interpreter crashes on strings that aren't valid UTF-8"
type: bug
status: review
priority: medium
labels: [interpreter, strings, parity]
---
`__read_file` decodes with `errors="surrogateescape"` ([[src/myla/interpreter.py#L784-L795]]), but `len`, `s[i]` and `__write` encode with plain `"utf-8"`, which rejects surrogates.

## Steps to reproduce

```bash
printf 'ab\xff\xfecd' > bin.dat
```
```myla
from std.fs import read_to_string
fun main() {
    match read_to_string("bin.dat") {
        Ok(s) => print(len(s))
        Err(e) => print("err")
    }
}
```

## Actual

The native binary prints `6`; the interpreter dies with `UnicodeEncodeError: … surrogates not allowed` ([[src/myla/interpreter.py#L820-L828]]).

## Done when

- [x] One helper encodes interpreter strings to bytes with `surrogateescape`, used by `len`, indexing, `print`, `__write`, `format`, `append`, `+` and map hashing
- [x] `chars()` on invalid UTF-8 behaves the same in both backends (the native decoder can read past the end on a truncated sequence: [[MYLA-17]])
- [x] Parity test with a binary file

## How

A `str` is bytes; the interpreter keeps it as a Python `str` with every byte that isn't part of valid UTF-8 escaped as a lone surrogate (`surrogateescape`, as `__read_file` and `build` already decoded).

- [[src/myla/interpreter.py]]: `_str_bytes` / `_bytes_str` for `len`, indexing, `append`, `__write`, `__read_file`, `__write_file` and `build`. `+` and `format` decode their result again when a sequence could have been split between the pieces (`_normalize`), so `byte(0xC3) + byte(0xA9) == "é"` and works as a map key, as natively. `chars` uses `_decode_chars`.
- [[src/myla/cli.py]]: stdout and stderr use `errors="surrogateescape"`, so `print` writes the original bytes, as natively.
- `chars()` semantics, the same in all four implementations: the scalar of each well-formed UTF-8 sequence, and U+FFFD for each byte that isn't part of one (stray continuation bytes, `C0`/`C1`/`F5`+ leads, truncated sequences, overlong forms, encoded surrogates, values above U+10FFFF). The native `__str_chars` in both code generators validates every sequence and never reads past the end (the second point of [[MYLA-17]]); the self-hosted interpreter uses the native builtin.

## Evidence

- [[tests/burn/test_invalid_utf8.py]] reads a binary file (stray bytes, a truncated 4-byte sequence, an overlong NUL, an encoded surrogate, `é`, `😀`, and a sequence cut off by the end) and checks `len`, every byte, `chars`, `print`, `+`, `format`, `==` and map keys, comparing raw stdout with the expected bytes for the Python interpreter, the Python native backend, the self-hosted compiler and the self-hosted interpreter. Before: the interpreter died with `UnicodeEncodeError: … surrogates not allowed`, and all three native decoders returned garbage (`2091236`, beyond U+10FFFF, for `FF FE`). After: all four pass.
- Bootstrap fixed point holds (6,091,753 bytes); unit, integration and burn suites pass.
