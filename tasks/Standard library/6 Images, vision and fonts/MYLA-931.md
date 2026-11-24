---
id: MYLA-931
title: "std.bytes: ByteReader, BitReader and their writers"
type: feature
status: backlog
priority: medium
labels: [stdlib, bytes, images]
---
Step 1 of [[Project/Standard-library-roadmap/Images-vision-and-fonts]]. Every codec reads big- and little-endian integers and bit streams. One tested set beats five private ones.

- **Owns:** the new parts of `lib/std/bytes.my`, [[Language/Standard-library/Bytes]]
- **Needs:** [[MYLA-930]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] `ByteReader { data, pos }`: `u8`, `u16_be/le`, `u32_be/le`, `u64_be/le`, `i16`/`i32` both orders, `f32_be/le`, `f64_be/le`, each an `Option` (`None` past the end, the position unchanged); `skip`, `take(n)`, `seek`, `remaining`
- [ ] `BitReader` MSB-first (JPEG, with `0xFF00` unstuffing as an option and markers reported; TIFF's LZW) and LSB-first (GIF's LZW, DEFLATE); `bits(n)` up to 32, `peek`, `align`
- [ ] `ByteWriter` and `BitWriter` (both bit orders) for the encoders
- [ ] Measured natively: reading 100 MB as `u32_be`s and as 13-bit codes, against the same loop by hand; within 20 % of it, or the reason why not
- [ ] std.compress's inflate moved onto `BitReader` if it costs no speed (its 100 MB benchmark, [[Language/Standard-library/Compress#speed]]), else left alone with the numbers
- [ ] `#test` cases on every public function that has values to compare (images up to about 16×16), test functions for the generic ones (D162), passing interpreted and `--native`, and on aarch64 (qemu) and wasm32 (Node)
- [ ] Its page below [[Language/Standard-library]] with a doc block that runs, the skill's `reference/stdlib.md`, and an example in `examples/`, registered
