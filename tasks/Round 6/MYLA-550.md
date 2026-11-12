---
id: MYLA-550
title: "R8 The library's D184 second pass: YAML's hex scalars, a buffered seek, bigint's bit length, zip's output limit"
type: bug
status: todo
priority: high
labels: [std, yaml, io, bigint, archive, round-6]
---
Work package R8 of [[Project/Review-2026-11-12]]. Files: `lib/std/yaml.my`, `io.my`, `bigint.my`, `unionfind.my`, `graph.my`, `archive.my`. D184: a parser returns an error, a bad argument is a named runtime error, wrapping only where defined. Found by the review's fuzzing of 11 parsers (201,300 inputs, plain and `--checked`) and its 17,861 extreme-argument calls.

- [ ] **`std.yaml` traps on a hex or octal scalar past `int64`** (high, old): `yaml.parse("mask: 0xFFFFFFFFFFFFFFFF\n")` is `runtime error: integer overflow` at `yaml.my:1139` under `myla run` and `--checked`, and a float in a plain build (`repro-r5/std/bug_yaml_hex_overflow.my`)
- [ ] **`Buffered.seek(SeekFrom.Current(k))`** subtracts the buffered count from `k`: int64's smallest value overflows at `io.my:594` where checked and is `InvalidInput` plain, which is what `MemoryStream` gives (`bug_buffered_seek.my`)
- [ ] **`bigint.from_int(5i64).shl(2147483646).bit_len()`** is -2147483647 in a plain build and `integer overflow` at `bigint.my:251` checked (`mag_bitlen`'s `(a.len() - 1) * 32`). Count in `int64` with a named error, or refuse the `shl` (`bl.my`)
- [ ] `unionfind.find`, `union`, `same`, `size_of` and `graph.bfs_dense`, `dijkstra_dense` give a raw `list index -1 out of bounds (len 3)` for an argument out of range; D184 asks for a message that names the argument
- [ ] **`archive.zip_read` has no output limit**: a bomb is `out of memory`; only `zip_list` with `zip_data(limit)` is safe, and the page doesn't say so
- [ ] A tar entry of 2^31 bytes or more is `BadHeader`, ustar's legal maximum included; undocumented
- [ ] `read_exact(n)` asks for `n` bytes in one read: `echo abc | exact 2000000000` under a memory limit is `out of memory`, not `None`
- [ ] A pax record with an empty key is accepted; `MemoryStream.write([])` after a seek past the end fills the gap
- [ ] The burn drivers of the format parsers built `--checked` too, as `test_archive`'s is: it would have caught the first box ([[MYLA-555]] has the generators)
