---
id: MYLA-376
title: "Swap wave 3's private helpers for the standard library's own"
type: chore
status: todo
priority: low
labels: [stdlib, cleanup]
---
Wave 3's lanes ([[Project/Standard-library-roadmap]]) couldn't import `std.str`, `std.char`, `std.list` or `std.hash` in a `lib/std` module: its native harness didn't build ([[MYLA-360]]). So they wrote private copies. MYLA-360 is fixed, and these can go:

- [ ] `std.text`: the parts of `words`, `pad_start`/`pad_end` (`spaces`, `char_count`) and `join`
- [ ] `std.grid`: the test helpers `ok`, `is`, `is_err`, `none`; `std.graph`: `has`
- [ ] `std.bitset`: SWAR `ones`, `highest`, `lowest`. They need a `count_ones`/`trailing_zeros` in `std.int` first, which it doesn't have
- [ ] `std.compress`: `crc32_part`, `adler32_part` (`std.hash`, or [[MYLA-359]]'s checksum module)
- [ ] `std.bigint`: `filled`, and loops instead of `extend`
- [ ] `std.btree`: `inserted`, `removed`, `key_or`, `value_or`
- [ ] `std.fs`: `bytes_of`, `text_of`, `hex_of`, `joined`, `root_of`
- [ ] `std.path`, `std.glob`: wave 2's ([[MYLA-326]])
- [ ] Each module's cases still pass interpreted and with `--native`, and their measurements don't get worse
