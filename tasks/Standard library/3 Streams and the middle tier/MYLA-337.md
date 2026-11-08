---
id: MYLA-337
title: std.random and std.uuid
type: feature
status: review
priority: medium
labels: [stdlib, random, wave-3]
---
Wave 3 of [[Project/Standard-library-roadmap]], roadmap #15, #65. A seeded generator is a value: a program that wants reproducible runs seeds it, and one that doesn't seeds it from the OS.

- **Owns:** `lib/std/random.my`, `lib/std/uuid.my`, `docs/Language/Standard-library/Random.md`, `docs/Language/Standard-library/Uuid.md`
- **Needs:** [[MYLA-336]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [x] `Rng`: PCG or xoshiro256**, `seeded(n)`, `from_os()`, `next_u64`, `int_in(lo, hi)` without modulo bias, `float`, `bool`, `shuffle`, `choice`
- [x] `std.uuid`: v4 and v7, parse and print
- [x] The generator checked against its reference outputs
- [x] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [x] Its page below [[Language/Standard-library]], with a doc block that runs

## Evidence

Built from master after wave 2 (1dd86a6).

- **`std.random`** ([[lib/std/random.my]], [[Language/Standard-library/Random]]): `Rng` is xoshiro256**, seeded by SplitMix64 as its authors recommend. PCG64 would need a 128-bit multiplication, four 64-bit ones in Myla. `seeded(seed: uint64)`, `from_os()` (32 bytes of `__random_bytes`), and the `var self` methods `next_u64`, `next_u32`, `below(n: uint64)`, `int_in(lo, hi)`, `int64_in(lo, hi)`, `float`, `boolean`, `shuffled<T>`, `choice<T>`. The ranges are half-open, as `for` ranges are; an empty one is a failure. `int_in`, `int64_in` and `below` use Lemire's method (the 64-bit form with a 64×64→128 high product made of 32-bit halves).
- **Names:** `bool` became `boolean`, because `bool` is a keyword (`expected method name, found 'bool'`). `shuffle` became `shuffled`: it returns a new list, since a method of `Rng` can't change a list it is given, and `r.shuffle(xs)` alone would do nothing without a word (D164 (4)).
- **`std.uuid`** ([[lib/std/uuid.my]], [[Language/Standard-library/Uuid]]): `Uuid { hi, lo }` (`#derive(Eq, Hash)`, `Ord`, `Format`), `v4()`, `v7()` (entropy from `__random_bytes(16)`, the time from `time.now_utc()`), `generator(rng)` with `g.v4()` and `g.v7(unix_ms)` for deterministic UUIDs, `parse` (the canonical form, either case), `from_bytes`, `nil`, `max`, `u.to_str()`, `u.bytes()`, `u.version()`, `u.unix_ms()`. `UuidError` is a bare enum (D168): `Length(int)`, `Syntax(int)`, `ByteLength(int)`, with `message()` and `Format`. A `Generator` holds the `Rng`, because a function given an `Rng` would draw from its own copy.
- **Reference outputs:** a Python port of `splitmix64.c` and `xoshiro256starstar.c` reproduces the published vectors: SplitMix64's first five numbers for 1234567, and xoshiro256**'s first ten for the state 1, 2, 3, 4, as the Rust crate `rand_xoshiro` pins them. The cases pin both, plus the port's numbers for `seeded`, `next_u32`, `below`, `int_in`, `int64_in`, `float`, `boolean` and `shuffled`. The UUID cases pin RFC 9562's examples A.3 (v4) and A.6 (v7), and the seeded generator's UUIDs, checked with Python's `uuid` module.
- **Tests first:** the cases are written against the port's numbers. A copy with xoshiro's `* 9` as `* 7` fails 19 of 41 cases. One whose `int_in` takes `next_u32() % n` fails 5, `int_in_has_no_modulo_bias` among them (half of the draws in the first third instead of a third). A copy of `std.uuid` with v7's time shifted by 12 and v4's version bits wrong fails 7 of 47.
- **Cases:** `myla test lib/std/random.my --stdlib lib`: 41/41 interpreted, `--native` 41/41, `--target aarch64-linux` 41/41. `lib/std/uuid.my`: 47/47 for each of the three. On `wasm32-wasi` (node), the harness stops at the first case that expects a panic (MYLA-370), so the full files pass 13/41 and 10/47 there. Copies without those cases pass 38/38 and 45/45. The generic and statistical checks are test functions: a shuffle is a permutation, the 6 orders of 3 elements, the places of an element, a die's faces and `choice`'s elements come up evenly, `int_in` has no modulo bias at 32 and 64 bits, `float` and `boolean` are fair, and a copy replays.
- **Burn tests:** after `scripts/bootstrap.sh`, `python3 -m unittest tests.burn.test_std_modules tests.burn.test_doc_blocks` passes (6 tests). Both pages' doc blocks run.
- **Measured** natively on x86-64, best of five: 100 million `next_u64` take 290 ms, about 345 million numbers a second. The reference C code at `gcc -O2` takes 126 ms, about 790 million a second. 10 million `int_in(1, 7)` take 50 ms. A million `g.v4().to_str()` take 220 ms. Check time of a hello-world (median of 15): 41 ms, 46 ms with `import std.random`, 49 ms with `std.time`, 52 ms with `std.uuid` (which imports both).
- **Found on the way:** a failed case shows a `uint64` of 2^63 or more as negative (`expected Uuid { hi: -7957569208247565536, … }`), interpreted and native. This is [[MYLA-361]], already filed.

## Decided (2026-11-08)

The owner kept the panics: `random.from_os()`, `uuid.v4()` and `uuid.v7()` fail when the system gives no entropy (or v7's clock is before 1970) instead of returning a `Result`, an exception to D164 (3). [[Language/Standard-library/Random]] and [[Language/Standard-library/Uuid]] say so.
