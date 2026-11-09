---
id: MYLA-369
title: "A primitive for str ↔ [uint8] in one copy, and StringBuilder capacity"
type: improvement
status: review
priority: medium
labels: [stdlib, primitives, performance]
---
Found by three wave 2 lanes. `std.bytes.to_str` ([[MYLA-329]]) appends a byte at a time, `std.io`'s `Read`/`Write` traits ([[MYLA-338]]) gained `read_str`/`write_str` so a descriptor's text isn't converted twice (50 MB of lines took 331 ms with `[uint8]` only, 75 ms with the `str` path), and `std.digest` ([[MYLA-328]]) has its own private `bytes_of`. A library module can't use the raw-memory primitives in the interpreter, and `StringBuilder` can't reserve.

- [x] A primitive (or builtin methods) converting a `str` to `[uint8]` and back in one allocation and one copy, on every target and in the interpreter
- [x] `StringBuilder` with a capacity
- [x] `std.bytes`, `std.io` (perhaps dropping `read_str`/`write_str`) and `std.digest` moved onto them, measured

## What was built

- `__str_to_bytes(s: str) -> [uint8]` and `__bytes_to_str(b: [uint8]) -> str`: std.rt's `str_to_bytes` and `bytes_to_str` in Myla (an `__alloc`, a `__copy_bytes`; the list's capacity is all its cell has), so every target has them with no code of its own; in the interpreter the host's (`bytes_to_value(__str_to_bytes(s))`, and a `StringBuilder` of the list's length). Primitives, not methods: they belong to `std.bytes` (D164's conventions), and a program's call is D100's warning as for every I/O primitive.
- `StringBuilder(n)`: the checker takes nothing or one `int32` (`examples/errors/type_sb_ctor_args.my` changed with its message, pinned in its `.stderr`), the lowering calls std.rt's `sb_with_capacity(n)` (an empty builder whose capacity is its whole cell; a negative `n` is 0), the interpreter evaluates `n` and starts empty.
- `std.bytes.from_str`/`to_str` are the primitives; `std.io`'s `bytes_of` and `text_of` too (a part of a list: a slice, then the copy), `BufferedWriter.write` converts once and appends, its buffer a `StringBuilder(capacity)`, `read_all` gathers text and converts once; `std.digest`'s `bytes_of`. `std.fs`'s and `std.process`'s `read`/`write` go through `std.bytes`, so they gained too.
- `read_str` and `write_str` stay: the measurement below says they no longer pay for themselves, but dropping them touches nine modules and the gaps lane's `std.io.copy`, so it is filed as its own decision, [[MYLA-399]].

## Evidence

- Before: the seed compiler (eaa905d's) doesn't know `__str_to_bytes` (`unknown function`); `StringBuilder(1)` was `StringBuilder() takes no arguments`. After: `tests/burn/test_platform_primitives.py`'s `Bytes` (a UTF-8 string and back, a list grown after it was made, empty ones, bytes that aren't UTF-8, a builder with a capacity, a negative one that grows, one that grows past it) passes interpreted and natively, and under `scripts/test-target.py aarch64-linux` and `wasm32-wasi`; `Warnings` holds both primitives to the primitive warning and their argument types. `std.bytes`' new `every_byte_round_trips` (all 256 values and back, copies not shared): `build/myla test lib/std/bytes.my --stdlib lib` 48/48 interpreted and `--native`; `io.my` 26/26, `digest.my` 62/62 both ways (`text_of`'s new cases among them).
- Measured natively on x86-64, 50 MB of lines of up to 120 bytes (2026-11-09, best of 3 unless said; other lanes used the machine):

  | What | eaa905d | Now |
  | --- | --- | --- |
  | `bytes.from_str` of 50 MB | 123 to 156 ms | 25 to 26 ms |
  | `bytes.to_str` of 50 MB | 180 to 209 ms | 26 ms |
  | 1 000 000 `BufferedWriter.write` of a 48-byte `[uint8]` to a descriptor | 110 to 118 ms | 23 to 28 ms |
  | `hmac_sha256_hex` of 50 MB | 477 to 610 ms | 390 to 427 ms |
  | 48 MB of 48-byte appends, `StringBuilder()` / `StringBuilder(48000000)` | 74 to 95 ms (no capacity) | 77 to 87 ms / 46 to 49 ms |
  | `ChildStdout.read` (`[uint8]`) of 256 MiB | 488 to 706 ms | 101 to 118 ms (`read_str` 115 to 125 ms) |

  Interpreted, 2 MB: `from_str` 11.6 to 12.1 s → 0.12 s, `to_str` 9.3 to 9.7 s → 0.07 s, 20 000 `BufferedWriter.write` 5.4 to 5.5 s → 1.1 to 1.2 s.
- `read_str` measured as the task asks: `stdin().read_line()` over the 50 MB through `read_str` (as built) 129 to 153 ms (median 132, seven runs interleaved); a variant whose `Buffered` pulls through `read` and `bytes.to_str` 100 to 148 ms (median 106); that variant with the conversions a byte at a time, as before, 289 to 487 ms (median 302, MYLA-338's 331 ms). Interpreted, 2 MB: 6.1 to 6.5 s through `read_str`, 6.6 s through `read`. So the `[uint8]` path costs nothing natively now, and about 5 % interpreted ([[MYLA-399]]).
