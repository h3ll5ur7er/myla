---
id: MYLA-440
title: "Interpreter: a uint64 map key's text in `map key … not found` is signed"
type: bug
status: done
priority: low
labels: [interpreter, round-5]
---
Found by [[MYLA-415]] (D183). The interpreter writes a missing map key with `py_repr` of its value, which for a `uint64` stored as the int64 of its bits is signed; native code (since MYLA-415) writes it unsigned, as the type says, so the two runners' texts differ for keys of 2^63 or more:

```myla
fun main() {
    let m: [uint64: int] = [1: 2]
    let k: uint64 = 18446744073709551615
    print(m[k])
}
```

`myla run`: `runtime error: map key -1 not found`; native: `runtime error: map key 18446744073709551615 not found`.

- [x] `index_error` writes the key by its type (`typed_repr`, as the test reports do, MYLA-361), so both runners print `18446744073709551615`
- [x] A case in `test_runtime_errors_carry_the_interpreters_values` ([[tests/burn/test_compiler_parity.py]])

## What was built

In [[selfhost/interp.my]]: `check_index`, the one place a missing key fails a program (a read, `m[k]`, and an index on the way to a place, `m[k][0] = 3`), writes the key with `typed_repr` by the map's key type (`index_key_type` of the index: the map's checked type at the index's target, a type parameter's its frame's (MYLA-414); an assignment's target, which the checker gives no type, its key's). `index_error` stays a free function without the checker: its message for a map (`missing_key`) is only replaced, so the type is looked up on the error path alone. `typed_repr` writes a `uint64` unsigned, alone or inside a tuple, a list, a struct or an enum key; every other integer width is stored as its value, which `py_repr` already writes as native code does (`int8 -128`, `uint32 4294967295`, `int64` MIN: the cases below). Shares the key-type plumbing (`place_in(c, k, kt)`) with [[MYLA-436]].

## Evidence

- **Failing first** (bccc624's `interp.my` in place): `test_runtime_errors_carry_the_interpreters_values`'s new cases `uint64_key`, `uint64_high_bit_key` (2^63: `-9223372036854775808` interpreted), `uint64_literal_key`, `uint64_tuple_key` (`(-1, 4294967295)`), `uint64_key_of_a_place` failed, `uint32_key` and `int64_key` passed; `test_runtime_errors_are_reported_alike`'s new `missing_uint64_key_in_generic_code` (`m[k]` in `fun look<K: Eq + Hash, V>`) failed with `map key -1 not found`. With the change: all pass, `map key 18446744073709551615 not found` on both runners.
- Before the change, by hand, 11 key types interpreted and native: the 5 of a `uint64` differed, `uint8`, `uint16`, `uint32`, `int8`, `int16`, `int64` agreed; after, all 11 agree.
- **Suites** (both tasks together): `scripts/test.sh fast` 848 tests OK (3 skipped); `test_compiler_parity`, `test_selfhost_interp`, `test_selfhost_cases` 260 OK; `build/myla test lib/std/set.my` (a generic written `eq`, interpreted) 7/7, `map.my` 11/11, `hash.my` 65/65; `scripts/test.sh` (all) 1,518 tests, one failure: `test_children_run_in_parallel` (native threads, `cpu 1.11 s, wall 1.05 s` against 1.5 times; it fails alone too at a load average of 9.8 on the 4 shared cores, and nothing here touches native code); `scripts/bootstrap.sh`: byte-identical fixed point (21,095,057 bytes), `selfhost/embedded_std.my` unchanged (no `lib/` change).

## Review 2026-11-12

Signed off in [[Project/Review-2026-11-12]], with a follow-up in [[MYLA-546]]: a `uint64` index of 2^64-1 is still reported as -1, and the REPL echoes a `uint64` signed.
