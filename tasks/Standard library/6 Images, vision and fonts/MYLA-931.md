---
id: MYLA-931
title: "std.bytes: ByteReader, BitReader and their writers"
type: feature
status: review
priority: medium
labels: [stdlib, bytes, images]
---
Step 1 of [[Project/Standard-library-roadmap/Images-vision-and-fonts]]. Every codec reads big- and little-endian integers and bit streams. One tested set beats five private ones.

- **Owns:** the new parts of `lib/std/bytes.my`, [[Language/Standard-library/Bytes]]
- **Needs:** [[MYLA-930]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [x] `ByteReader { data, pos }`: `u8`, `u16_be/le`, `u32_be/le`, `u64_be/le`, `i16`/`i32` both orders, `f32_be/le`, `f64_be/le`, each an `Option` (`None` past the end, the position unchanged); `skip`, `take(n)`, `seek`, `remaining`. Also `i8`, `u24_*`, `i64_*`, `has`, `at_end`, `take_rest`, `eat(sig)` and `peek_u8`
- [x] `BitReader` MSB-first (JPEG, with `0xFF00` unstuffing as an option and markers reported; TIFF's LZW) and LSB-first (GIF's LZW, DEFLATE); `bits(n)` up to 32, `peek`, `align`. Two types with the same methods, `MsbBitReader` (`msb_reader`, `jpeg_reader`) and `LsbBitReader` (`lsb_reader`), so the hot path tests no bit order; also `skip_bits`, `bits_left`, `byte_pos`, `refill`, and for JPEG `marker`, `marker_pos`, `skip_marker`
- [x] `ByteWriter` and `BitWriter` (both bit orders) for the encoders: `ByteWriter` (every `put_` of the reads, `put_bytes`, `put_str`, `put_zeros`, the `set_` patches), `MsbBitWriter` (`msb_writer`, `jpeg_writer` with stuffing, 1-bit padding and `put_marker`) and `LsbBitWriter`
- [x] Measured natively: reading 100 MB as `u32_be`s and as 13-bit codes, against the same loop by hand; within 20 % of it, or the reason why not. Not within 20 %: 1.7 to 2.6 times as slow. The reason is the compiler, and the page gives it with the numbers ([[Language/Standard-library/Bytes#speed]])
- [ ] std.compress's inflate moved onto `BitReader` if it costs no speed (its 100 MB benchmark, [[Language/Standard-library/Compress#speed]]), else left alone with the numbers. After wave 1: another lane edits `lib/std/compress.my` now. From the numbers below, a move as plain `bits()` calls would cost speed; inflate would have to keep the buffer in locals ("In a hot loop" on the page)
- [ ] `#test` cases on every public function that has values to compare (images up to about 16×16), test functions for the generic ones (D162), passing interpreted and `--native`, and on aarch64 (qemu) and wasm32 (Node). Interpreted, `--native` and wasm32 pass; aarch64 not run: qemu-aarch64 isn't installed on this machine (the test binary builds for aarch64)
- [x] Its page below [[Language/Standard-library]] with a doc block that runs, the skill's `reference/stdlib.md`, and an example in `examples/`, registered

## Evidence

- **Tests, written first:** the test functions went in before the code, and `build/myla test lib/std/bytes.my` failed with 15 type errors (the API missing). Then 183/183 cases pass interpreted, `--native` (checked) and `--target wasm32-wasi` under Node (`MYLA_EMULATOR="node tools/wasm/run.mjs"`). They are `#test` cases on every method with values to compare, and test functions for each bit reader against a bit-by-bit reference (random widths 0 to 32, skips, alignments, a start inside the data, both orders), writer round trips (400 random widths, MSB, LSB, JPEG), every integer and float type both ways, positions after short reads, and JPEG stuffing, fill bytes, markers and restarts.
- **Fuzz:** `bit_readers_fuzz` runs 300 random sequences of every operation (invalid widths and starts included) on random bytes rich in 0xFF, 0x00 and 0xD0, against a byte-at-a-time reference of the JPEG segment. A mutation check (stuffing not counted in `refill`) makes it fail at trial 9. The same fuzz as a program over the public API ran 200,000 sequences (12 million operations) natively, built plain and `--checked`: all pass, 0.56 s each.
- **Example:** `examples/binary_data.my` (8/8 cases; registered in `test_examples_run.py` and `test_examples_compile.py`, both pass). The doc block's output matches interpreted and native.
- **Benchmark:** `benchmarks/bytes_std.my` (12/12 cases), natively on x86-64, best of 5 over 100 MiB, on a shared machine (load about 2):

  | What | Library | By hand |
  | --- | --- | --- |
  | `u32_be` | 136 ms | 78 ms (1.7×) |
  | `u32_be`, `has(4)` first | 181 ms | |
  | 13-bit codes, MSB | 405 ms | 153 ms (2.6×) |
  | 13-bit codes, LSB | 483 ms | 216 ms (2.2×) |
  | the same with the reader's fields used in the loop | 411 ms | (1.9×) |
  | `peek(16)` + `skip_bits` | 1090 ms | |
  | 13-bit codes written, MSB | 508 ms | 298 ms (1.7×) |

  Why it isn't within 20 %, from an experiment (not committed: 50 MiB, LSB): the reader declared in the caller's own module took 217 to 267 ms, a variant without the `Option` 219 to 232 ms, and the fields used inline with no call per code 169 to 197 ms, against 90 ms by hand. So neither the `Option` nor the bounds checks cost the time: the state in a struct does, loaded and stored through `self`'s pointer (the IR shows `load [%t0 + 24]` and similar for each field), and the call, which isn't inlined across modules (`inline.my` copies only small scalar leaf functions of the same module). Fixing that is compiler work (cross-module inlining, or scalar replacement of a struct's fields through a loop), and there is no open task for it. Proposed as one.
- **Check time** (`myla check` of a 3-line program importing std.bytes, 7 runs each): 8 ms before, 9 to 10 ms after; a program without imports takes 8 ms. About 1.5 ms more, which isn't noticeable, so the types stay in std.bytes and not a module of their own. `scripts/bootstrap.sh` passes with the new bytes.my.
- **Found:** a call that leaves out a default argument inside a `#test(...)` argument (`#test(msb_reader([1u8]))[…]` with `start: int = 0`) crashes the interpreter's test runner: `runtime error: list index 1 out of bounds (len 1)` at `selfhost/interp.my:4867` (`enter_func`: the argument list isn't filled with the default). `--native` passes. Repro: a function `boxed(v: int, extra: int = 0)` and `#test(boxed(2))[2]` on a method. The cases here pass the argument explicitly.
