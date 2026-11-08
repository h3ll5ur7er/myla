# std.uuid

UUIDs of RFC 9562 ([[MYLA-337]]): version 4, random, and version 7, a Unix time in milliseconds and random bits, read and written in the canonical 8-4-4-4-12 form. `uuid.v4()` and `uuid.v7()` take their random bits from the system and v7's time from the wall clock; a `Generator` takes them from an `Rng` of [[Language/Standard-library/Random]] and v7's time from its caller, so that a seeded one makes the same UUIDs on every run. The module imports `std.random` and `std.time`.

```myla
import std.random as random
import std.uuid as uuid

fun main() {
    var g = uuid.generator(random.seeded(1))
    let a = g.v4()
    print(a)
    print(a.version())
    let b = g.v7(1645557742000)
    print(f"{b} {b.unix_ms().unwrap_or(0)}")
    match uuid.parse("017F22E2-79B0-7CC3-98C4-DC0C0C07398F") {
        Ok(u) => print(f"{u} version {u.version()}")
        Err(e) => print(e.message())
    }
    match uuid.parse("017f22e2-79b0-7cc3-98c4+dc0c0c07398f") {
        Ok(u) => print(u.to_str())
        Err(e) => print(f"{e}")
    }
    let c = g.v7(1645557742001)
    print(b.cmp(c))
    print(uuid.v4().version())
    print(uuid.v7().to_str().len())
}
// output:
// b3f2af6d-0fc7-40c5-853b-559647364cea
// 4
// 017f22e2-79b0-7514-a42e-1c7bc266a3a7 1645557742000
// 017f22e2-79b0-7cc3-98c4-dc0c0c07398f version 7
// bad UUID at byte 23
// -1
// 4
// 36
```

| Function | Result |
| --- | --- |
| `v4() -> Uuid` | A random UUID, version 4: 122 bits of the system's entropy (`__random_bytes`). A system that gives none is a failure |
| `v7() -> Uuid` | A UUID of the time now, version 7: the wall clock's Unix time in milliseconds (`time.now_utc()`) and 74 bits of the system's entropy. A clock before 1970 is a failure |
| `generator(rng: random.Rng) -> Generator` | A source of UUIDs whose random bits come from `rng`: `generator(random.seeded(1))` makes the same UUIDs on every run |
| `parse(s: str) -> Result<Uuid, UuidError>` | The UUID in the text `s`, in the canonical form, the hex digits in either case. Braces, a `urn:uuid:` and the form without hyphens are errors |
| `from_bytes(b: [uint8]) -> Result<Uuid, UuidError>` | The UUID of the 16 bytes `b`, in the order `u.bytes()` gives them |
| `nil() -> Uuid`, `max() -> Uuid` | The UUID of every bit 0, of every bit 1 |

| Method | Result |
| --- | --- |
| `g.v4() -> Uuid` | A version 4 UUID of two numbers of the generator's `Rng`. Needs a `var` place |
| `g.v7(unix_ms: int64) -> Uuid` | A version 7 UUID of the time `unix_ms` and two numbers of the generator's `Rng`. A time outside 0 to 2^48 - 1 (the year 10889) is a failure. Needs a `var` place |
| `u.to_str() -> str` | The canonical text, 8-4-4-4-12 lowercase hex digits; `print(u)` and `f"{u}"` write it too (`Format`; the spec is ignored) |
| `u.bytes() -> [uint8]` | The 16 bytes, in the order of the text |
| `u.version() -> int` | The version: 4, 7, or another for a UUID that was read (0 for the nil UUID, 15 for the max one) |
| `u.unix_ms() -> Option<int64>` | The Unix time in milliseconds of a version 7 UUID; `None` for another version |
| `u.cmp(other: Uuid) -> int` | -1, 0 or 1, the order of the bytes and so of the texts (`Ord`) |

A `Uuid` is a struct of two `uint64`s, `hi` (the first eight bytes, most significant first) and `lo` (the last eight), with `#derive(Eq, Hash)`: a map key or a `Set` element. A `UuidError` is a bare enum (D168) with `message()` and `Format`: `Length(n)`, a text of `n` bytes, not 36; `Syntax(at)`, no hex digit or no hyphen at the byte `at`; `ByteLength(n)`, a list of `n` bytes, not 16.

A `Generator` is a value, as its `Rng` is: keep it in a `var` or a struct field, as [[Language/Standard-library/Random#A generator is a value]] says. Its v7 takes the time from its caller, so a test can fix it; `time.now_utc()` gives the time now.

## How it works

Both versions put the version in the four bits after the 48th (the third group's first hex digit) and the variant of RFC 9562, the bits `10`, at the top of the fourth group. A v4 UUID's other 122 bits are random. A v7 UUID has the Unix time in milliseconds in its first 48 bits, then the version, 12 random bits, the variant and 62 random bits (RFC 9562's layout without its optional counter). A UUID of a later millisecond sorts after one of an earlier, as bytes, as text and with `cmp`, which keeps database indexes in order; two of the same millisecond are in a random order.

`uuid.v4()` reads 16 bytes of the system's entropy for every UUID, as Python's `uuid4` does, rather than drawing from a generator, so that a UUID can't be worked out from others. A `Generator`'s UUIDs come from xoshiro256**, which is fine for identifiers but not for secrets.

The tests pin RFC 9562's examples (A.3 for version 4, `919108f7-52d1-4320-9bac-f847db4148a8`; A.6 for version 7, `017f22e2-79b0-7cc3-98c4-dc0c0c07398f`), the UUIDs of `generator(random.seeded(1))` checked with Python's `uuid` module, `parse`'s errors, and that UUIDs of the system and of the clock have their version, variant and time and read back from their text and bytes.

## Speed

Measured natively on x86-64, best of five runs: a million `g.v4().to_str()` take 220 ms.
