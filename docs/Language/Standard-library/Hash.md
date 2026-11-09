# std.hash

The `Hasher`'s methods and wyhash ([[MYLA-327]]); the checksums, FNV-1a, CRC-32 and Adler-32, are [[Language/Standard-library/Checksum]]'s since [[MYLA-359]] (D166), as every program checks this module. The `Hasher` is what the `Hash` trait passes through (D163, [[MYLA-313]]): the struct and the trait are the prelude's, so every module can name them, and this module, which every program outside `std` has without an import (as std.str is, D164), gives the hasher its methods and the built-in types their `Hash` impls. The module imports nothing.

```myla
import std.hash as hash

struct Point {
    x: int,
    y: int,
}

fun point_hash(p: Point) -> uint64 {
    return hash.new().add_i32(p.x).add_i32(p.y).finish()
}

fun main() {
    var h = hash.new()
    h = h.add_str("apple")
    h = h.add_u8(3)
    print(h == hash.new().add_str("apple").add_u8(3))
    print(point_hash(Point { x: 1, y: 2 }) == point_hash(Point { x: 2, y: 1 }))
    print(f"{hash.wyhash("abc", 2):#x}")
}
// output:
// true
// false
// 0x32dd92e4b2915153
```

`wyhash` takes a `str`, and its `_bytes` form a `[uint8]`; the two give the same result for the same bytes.

| Function | Result |
| --- | --- |
| `new() -> Hasher` | A hasher with the fixed seed, `with_seed(0)` |
| `with_seed(seed: uint64) -> Hasher` | A hasher with its own seed |
| `wyhash(s, seed: uint64) -> uint64`, `wyhash_bytes(b, seed)` | The Hasher's algorithm at once: `with_seed(seed).add_str(s).finish()` |

## The Hash trait

```myla
import std.hash as hash

#derive(Eq, Hash)
struct Point {
    x: int,
    y: int,
}

fun digest<T: Hash>(x: T) -> uint64 {
    return hash.new().add(x).finish()
}

fun main() {
    print(digest(Point { x: 1, y: 2 }) == hash.new().add_i32(1).add_i32(2).finish())
    print(digest((1, 2)) == digest(Point { x: 1, y: 2 }))
    print(digest([1, 2]) == digest([1, 2]) && digest([1, 2]) != digest([2, 1]))
}
// output:
// true
// true
// true
```

`trait Hash { fun hash(self, h: Hasher) -> Hasher }` and `struct Hasher { state: uint64 }` are in the prelude (with an `impl Eq` for the hasher); this module gives `Hasher` its methods, among them `add<T: Hash>(x) -> Hasher`, which is `x.hash(h)` and is what a `Hash` impl calls for each field: `h.add(self.x).add(self.y)`. So `Hasher` is a name of every module, and `hash.Hasher` isn't one ([[Language/Methods-and-traits#hash]] has the trait, `#derive(Hash)` and the rules).

| Type | Its `hash(h)` |
| --- | --- |
| the integers | `h.add_i8(x)` … `h.add_u64(x)`: the value widened to 64 bits |
| `char`, `bool` | `h.add_char(x)`, `h.add_bool(x)` |
| `str` | `h.add_str(x)` |
| `[T]`, `T: Hash` | its length as a `uint64`, then each element's `hash`, so `([1], [2, 3])` and `([1, 2], [3])` differ |
| a tuple of `Hash` elements | each element's `hash` in turn (the language's own, as no impl can name a tuple) |
| `#derive(Hash)` | its fields in order; an enum's variant index as a `uint64`, then its payload |

Floats aren't `Hash`. A map doesn't hash its keys through the `Hasher`: an integer, `char`, `bool` or `str` key has std.rt's own hash, and natively a compound key is hashed by its parts, a type's written `hash` called (the interpreter does the same); the order of a map is its insertion order (D105), so no hash shows.

## The Hasher

A `Hasher` is a value. Myla has no `var` parameters, so each `add` takes the hasher and gives back a new one: `h = h.add_u64(x)`, or a chain, `hash.new().add_u64(a).add_str(s).finish()`. A hasher can be finished, added to and finished again.

| Method | Adds |
| --- | --- |
| `add_u64(x: uint64) -> Hasher` | A 64-bit word. The other integer adds widen to it |
| `add_u8`, `add_u16`, `add_u32`, `add_i8`, `add_i16`, `add_i32`, `add_i64` | The integer widened to 64 bits, a signed one sign-extended, so `add_u8(255)` is `add_u64(255)` and `add_i8(-1)` is `add_i64(-1)` |
| `add_bool(x)`, `add_char(x)` | 1 or 0; the code point |
| `add_str(s)`, `add_bytes(b)` | The bytes and their length |
| `finish() -> uint64` | The hash of what was added |

Equal values added in the same order give equal hashes. A different order gives a different hash, and so does the same text split differently between strings: the length of each string goes into its hash, so `add_str("ab").add_str("c")` isn't `add_str("a").add_str("bc")`. An integer type isn't added, only the value: `add_u8(1)` and `add_u64(1)` are equal. A `Hash` impl that adds a type's fields in order is right as long as equal values add equal fields. Floats have no `add`: a hand-written impl may add `math.to_bits(x)`.

The seed is fixed, so a hash is the same in every run, in the interpreter and natively on each target. Don't store hashes, though: once maps get a seed of their own, `new()` may change. None of these hashes is cryptographic, and with a fixed seed none resists inputs made to collide; [[MYLA-328]]'s `std.digest` has the cryptographic ones.

### How it works

The algorithm is wyhash, final version 4 (Wang Yi's, public domain; Zig's `std.hash.Wyhash` is the same). Its step is a *folded multiplication*: multiply two 64-bit words to 128 bits and xor the two halves. The state is one word:

- `with_seed(seed)` sets it up as wyhash does, `seed ^ mix(seed ^ S0, S1)`.
- `add_u64(x)` is one folded multiplication, `mix(state ^ x, S1)`, the construction of foldhash, the default hasher of Rust's hashbrown.
- `add_str(s)` runs wyhash over `s`, seeded with the state. So `with_seed(k).add_str(s).finish()` is exactly wyhash's value for `s` and `k`, and Zig's test vectors for wyhash check the Hasher as well.
- `finish()` gives the state, which a folded multiplication has just mixed.

Myla has no 128-bit integer, so the product is built from four 32 × 32-bit ones.

### Why wyhash and not SipHash-1-3

Measured natively on x86-64, best of three runs, with both written the same way in Myla (100 MB of input, 10 million small keys):

| | wyhash | SipHash-1-3 |
| --- | --- | --- |
| One `uint64` key, hasher to `finish` | 6.1 ns | 14.0 ns |
| Two `uint64`s | 9.2 ns | 18.2 ns |
| A 13-byte string | 16.4 ns | 20.5 ns |
| 100 MB at once | 1533 MB/s | 1275 MB/s |

wyhash is about twice as fast on the integer keys that a `Hash` impl adds most, and faster on strings and long input too, where reading the bytes one at a time costs both the same. Its state is one word, while SipHash keeps four, a partial word and a length: seven words to pass back from every `add`, and the measured SipHash hasher handled only whole words. SipHash's strength is resisting collisions made on purpose, but only with a secret random key; with the fixed seed it has none, so it buys nothing here. Both versions measured gave the values of a model in Python, whose wyhash passes Zig's test vectors and whose SipHash rounds pass the reference implementation's 64 vectors of SipHash-2-4.

## Speed

Natively on x86-64, the best of five runs over 100 MB (100,000,000 bytes), on a machine shared with other work:

| Function | `str` | `[uint8]` |
| --- | --- | --- |
| The Hasher, `add_str` / `add_bytes` (wyhash) | 1496 MB/s | 1496 MB/s |

A key of two `int32`s takes 8.7 ns from `new()` to `finish()`, a 13-byte string 16.1 ns. Every byte is read with a bounds check. std.checksum's FNV-1a, measured the same way, runs at about 950 MB/s.

## Tests

The vectors are published ones, Zig's tests of wyhash. A model of wyhash in Python, checked against those vectors, gives the rest: wyhash across its 16- and 48-byte boundaries, at every length up to 130, and over 10,000 bytes. Test functions check that the `str` and `[uint8]` forms agree and that the Hasher gives wyhash. The module's 65 cases (std.checksum has the checksums' 32) pass interpreted and natively.
