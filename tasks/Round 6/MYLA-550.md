---
id: MYLA-550
title: "R8 The library's D184 second pass: YAML's hex scalars, a buffered seek, bigint's bit length, zip's output limit"
type: bug
status: review
priority: high
labels: [std, yaml, io, bigint, archive, round-6]
---
Work package R8 of [[Project/Review-2026-11-12]]. Files: `lib/std/yaml.my`, `io.my`, `bigint.my`, `unionfind.my`, `graph.my`, `archive.my`. D184: a parser returns an error, a bad argument is a named runtime error, wrapping only where defined. Found by the review's fuzzing of 11 parsers (201,300 inputs, plain and `--checked`) and its 17,861 extreme-argument calls.

- [x] **`std.yaml` traps on a hex or octal scalar past `int64`** (high, old): `yaml.parse("mask: 0xFFFFFFFFFFFFFFFF\n")` is `runtime error: integer overflow` at `yaml.my:1139` under `myla run` and `--checked`, and a float in a plain build (`repro-r5/std/bug_yaml_hex_overflow.my`)
- [x] **`Buffered.seek(SeekFrom.Current(k))`** subtracts the buffered count from `k`: int64's smallest value overflows at `io.my:594` where checked and is `InvalidInput` plain, which is what `MemoryStream` gives (`bug_buffered_seek.my`)
- [x] **`bigint.from_int(5i64).shl(2147483646).bit_len()`** is -2147483647 in a plain build and `integer overflow` at `bigint.my:251` checked (`mag_bitlen`'s `(a.len() - 1) * 32`). Count in `int64` with a named error, or refuse the `shl` (`bl.my`)
- [x] `unionfind.find`, `union`, `same`, `size_of` and `graph.bfs_dense`, `dijkstra_dense` give a raw `list index -1 out of bounds (len 3)` for an argument out of range; D184 asks for a message that names the argument
- [x] **`archive.zip_read` has no output limit**: a bomb is `out of memory`; only `zip_list` with `zip_data(limit)` is safe, and the page doesn't say so
- [x] A tar entry of 2^31 bytes or more is `BadHeader`, ustar's legal maximum included; undocumented
- [x] `read_exact(n)` asks for `n` bytes in one read: `echo abc | exact 2000000000` under a memory limit is `out of memory`, not `None`
- [x] A pax record with an empty key is accepted; `MemoryStream.write([])` after a seek past the end fills the gap
- [x] The burn drivers of the format parsers built `--checked` too, as `test_archive`'s is: it would have caught the first box ([[MYLA-555]] has the generators)

## What changed

- **YAML (B5).** `resolve` multiplied on after it knew a `0o`/`0x` value passed int64 (`if !big` now guards it), so it gives the nearest `Float` without a trap. `parse` refuses such a scalar where it is a value with the new kind `OutOfRange` (`1:7: an integer in base 8 or 16 outside int64's range`); a key stays its text (`Item.range`, checked by `Parser.value` at the four places an item becomes a value). A decimal integer past int64 stays a `Float`, as the page and `std.json` have it. Swept: `std.yaml`'s escapes (at most 8 hex digits) can't overflow.
- **`Buffered.seek(Current(k))`**: a `k` that would pass int64's smallest when the buffered bytes are taken off is `InvalidInput`, as `MemoryStream` gives.
- **bigint**: a number holds at most 2^26 - 1 limbs (2,147,483,616 bits, 256 MiB; `MAX_LIMBS`, `MAX_BITS`), so `bit_len` and every bit position the module computes in an `int` fit. `shl` and `pow` refuse a larger result before they compute, naming the shift or the exponent (`bigint.shl: a shift of 2147483646 makes more than 2147483616 bits`); `*` refuses operands whose limbs together pass it (`bigint: a product of more than 2147483616 bits`); `make`, which every other result goes through, refuses the rest (`bigint: a number of more than 2147483616 bits`).
- **union-find and the dense graph forms**: `find`, `union`, `same`, `size_of` name the method and the element (`unionfind.find: element 3 is out of range for 3 elements`), `new(-1)` is `unionfind.new: a negative number of elements -1`; `bfs_dense` and `dijkstra_dense` name a bad start, a bad neighbour (`bfs_dense: node 2 has a neighbour 3, out of range for 3 nodes`) and a negative `n`; with `n == 0` they give `[]` whatever the start (before, an index error). The neighbour test is inline and calls only on failure: as a call per edge it cost a third of `bfs_dense`'s time.
- **`zip_read(b, max_output = 0x7FFFFFFF)`**: the entries' sizes from the directory added up and checked against `max_output` before any data is read (`TooLarge`); each entry is then decompressed as `zip_data` does, up to its size, so the entries take no more memory than `max_output`. A negative `max_output` is a runtime error, as for `zip_data`. `TooLarge`'s message is now "data longer than max_output or than a list holds".
- **tar**: an entry of 2^31 bytes or more (ustar's largest, 8 GiB - 1, among them) is `TooLarge`, not `BadHeader`: its data would be a list. Documented. A pax record whose key is empty is `BadHeader`.
- **`read_exact(n)`** asks each read for what it still needs but at most 4 KiB more than it holds (`exact_ask`), so the reads double and a count past the input's end isn't allocated; the async form too.
- **`MemoryStream.write([])`** is `Ok(0)` and leaves a gap after a seek past the end unfilled, as a file's empty write does.
- **The burn drivers built `--checked`**: `test_yaml` (the broken texts, and a new corpus `YamlNumbers` of 1,953 integers in bases 10, 8 and 16 around int64's limits, signed, with leading zeros and random lengths, each checked against Python), `test_toml` (both corpora, also under `MYLA_TEST_TARGET`), `test_xml` (the well-formed and broken corpora), `test_compress` (the corrupted inputs: exit status and error the same; the output only on success, as a stream's output before its error depends on how the pipe cut the input) and `test_regex` (10,000 patterns and counted repetitions past int32) each run the driver built plain and checked and want the same answers.

## Open decision (proposal)

D184 says a parser of outside input returns its error for a number out of range. YAML's core schema reads `[-+]?[0-9]+`, `0o…` and `0x…` as integers of any size; the page read those past int64 as a `Float`, "as in `std.json`". Built: **(c) an error for `0o`/`0x` past int64, a `Float` for a decimal one.** A base-8 or base-16 integer is a mask or a mode, whose nearest float is a different number (0xFFFFFFFFFFFFFFFF is 2^64), while a large decimal is a quantity a float rounds, as JSON readers do. Alternatives: (a) a `Float` for all three (the page as it was: no trap, but the mask silently changes); (b) `OutOfRange` for all three (the strictest reading of D184, but unlike `std.json` and a change for decimals that read fine today).

## Evidence

Each item's test failed before the change and passes after:

| Item | Test | Before | After |
| --- | --- | --- | --- |
| B5 | `parse`'s 9 new cases; `resolve`'s 3; `test_yaml.YamlNumbers` | `bug_yaml_hex_overflow.my`: `integer overflow` at `yaml.my:1139` interpreted and `--checked`, `{"mask":1.8446744073709552e+19}` plain | `1:7: an integer in base 8 or 16 outside int64's range` on all three |
| Buffered seek | `buffered_seeks` (4 new asserts) | `FAIL buffered_seeks: runtime error: integer overflow` | passes; `bug_buffered_seek.my` is `Err(invalid input (InvalidInput))` interpreted, plain and `--checked` |
| bigint | `BigInt.shl` #2, #3, `BigInt.pow` #4, #5 | `bl.my`: -2147483647 plain | `runtime error: bigint.shl: a shift of 2147483646 makes more than 2147483616 bits` interpreted and plain |
| union-find, graph | `new` #3, `find` #2, #3, `union` #3, `same` #3, `size_of` #2; `dense_out_of_range` #1 to #8 | 14 failures: `list index -1 out of bounds (len 3)` and the like | 21/21, 26/26 |
| zip_read | `zip_read` #6 to #8 | #6: `Ok`, #8: `NotZip` | passes; 3 MB of three 1 GiB entries under a 1.5 GB limit: `error: data longer than max_output` (before: `runtime error: out of memory`) |
| tar, pax | `tar_entry_too_large`, `pax_records` #5, #6 | `FAIL tar_entry_too_large` (BadHeader), #5 `Ok([('', 'abc')])` | passes |
| read_exact | `exact_count_past_the_end`, `exact_ask`'s 4 | `FAIL: asked for 2000000000` | passes; `echo abc \| exact 2000000000` under `ulimit -v 400000`: `short` (before `out of memory`); `read_exact(40000000)` from a pipe 110 ms (before 122 ms) |
| empty write | `memory_seeks` (1 new assert) | `0/1 passed` | passes |

- The module cases, interpreted, `--native` (built checked, as `myla test` builds), `--target aarch64-linux` and `--target wasm32-wasi`: yaml 209/209, io 35/35, bigint 142/142, unionfind 21/21, graph 26/26, archive 118/118, each on all four.
- Burn tests: `test_yaml`, `test_toml`, `test_xml`, `test_compress`, `test_regex`, `test_archive` OK.
- `bfs_dense` over a 1000 x 1000 grid, natively, best of five: 33 to 36 ms (31 to 33 before; the neighbour test).
- The review's extreme-argument generator (`repro-r5/std/gen.py`, groups `seq` and `cont`, 6,184 calls on `myla run`, a plain and a `--checked` build): no raw index error, overflow or signal is left in `std.bigint`, `std.io`, `std.unionfind` or the dense graph searches; what still differs there is a count of 2^30 and more, which the interpreter times out on and native code runs (`bigint.shl`) or is out of memory for (`bfs_dense(1073741823, 0)`), as `list.filled` of the same size.
- `scripts/test.sh fast`, then `test_std_modules`, `test_lsp`, `test_doc_blocks`, `test_overflow` (217 tests OK), then `scripts/test.sh` once: 1,549 tests, 3 failures. `test_embedded_std` and `test_installed`'s language-server case expect `selfhost/embedded_std.my`, which is behind `lib/` until the integrator's seed commit; `test_children_run_in_parallel` passes alone (load: the machine is shared by six lanes). `scripts/bootstrap.sh` on the result: byte-identical fixed point (24,059,779 bytes).
- A new bug seen beside `read_exact`: a read of `n` bytes from a descriptor allocates `n` first, [[MYLA-572]] (the runtime lane's `rt.my`).
