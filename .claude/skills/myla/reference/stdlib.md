# Standard library API index

Read from the source, `lib/std/*.my` (November 2026); the prose reference is `docs/Language/Standard-library.md` and one page per module below it. Re-check a signature with `grep -n "fun name" lib/std/<module>.my` before relying on a detail.

Implicit modules (methods in every program, no import): `std.str`, `std.char`, `std.int`, `std.float`, `std.list`, `std.option`, `std.map`, `std.hash`.

Other modules: `std.algebra`, `std.archive`, `std.args`, `std.bench`, `std.bigint`, `std.bitset`, `std.btree`, `std.bytes`, `std.cache`, `std.checksum`, `std.compress`, `std.csv`, `std.deque`, `std.digest`, `std.encoding`, `std.fmt`, `std.fs`, `std.glob`, `std.graph`, `std.grid`, `std.heap`, `std.http`, `std.ini`, `std.io`, `std.ioerror`, `std.iter`, `std.json`, `std.log`, `std.math`, `std.net`, `std.num`, `std.path`, `std.platform` (with `std.rt`: internal), `std.process`, `std.random`, `std.regex`, `std.set`, `std.signal`, `std.slice`, `std.task`, `std.term`, `std.test`, `std.text`, `std.time`, `std.toml`, `std.unionfind`, `std.url`, `std.uuid`, `std.vector` (with `std.matrix`, `std.quaternion` and the `32` twins), `std.xml`, `std.yaml`, and the gdb helper `lib/debug/myla_gdb.py`.

## Conventions

A method in an `impl` has no `pub` of its own and follows its type (public type: callable wherever the value is). `pub` free functions are reached as `m.f(…)` after `import std.m as m`. Defaults are trailing parameters with `= value` (D136): they can be left out, but there are no named arguments.

**Implicit modules** (`str`, `char`, `int`, `list`, `option`, `map`, `hash`): their methods on builtin types work in every program with no import (D164). They bind **no names**: their `pub` functions and types need an import (`import std.list as list_m`, `from std.list import ListIter`). Naming `ListIter<int>` without the import gives the misleading error `type 'ListIter' is not generic`. Modules of `lib/std/` don't get them; they import what they use.

Builtin methods (compiler, not std; an `impl` can't redefine them): `len()` on lists, maps, `str` and `StringBuilder`; `xs.push(v)` and `xs.pop()`; `m.contains(k)`, `m.keys()` and `m.remove(k)` (returns `()`); `s.chars()`; `sb.append(s)`, `sb.append(s, start, end)`, `sb.append_byte(b)`, `sb.append_char(c)` and `sb.build()`; `wrapping_add`, `wrapping_sub`, `wrapping_mul` and `wrapping_neg` on every integer.

None of these exist: `s.is_empty()`, `xs.is_empty()`, `xs.min()`, `xs.max()`, `xs.first()`, `opt.unwrap()`. Use `len() == 0`, `iter.min(xs.iter())` or `xs.min_by(…)`, and `opt.unwrap_or(…)`. Floats have methods (`x.sqrt()`, implicit `std.float`, D199).

```myla
import std.iter as iter
import std.num as num

fun main() {
    let words = "  b a b  ".trim().split(" ")      // implicit std.str
    var counts: [str: int] = [:]
    for w in words {
        counts.update(w, 0, (n) => n + 1)            // implicit std.map
    }
    let n = num.parse_int32("3").unwrap_or(0)        // Result<int32, ParseIntError>
    let big = [4, 9, 2].iter() |> iter.max()         // no xs.max(): Option<int>
    print(f"{counts.get_or("b", 0)} {big.unwrap_or(0)} {2.pow(n as uint32)}")
}
// output:
// 2 9 8
```


Notation: `fun f(a: A) -> R` is a module function (`mod.f(…)` after `import std.mod as mod`); indented `.m(…)` lines are methods (no `pub` on methods: every method of an `impl` is public). `async` = must be `await`ed, and only in async code. `var self` methods need a `var` receiver. Prose: `docs/Language/Standard-library/<Module>.md` (Archive, Bigint, Bitset, Btree, Cache, Checksum, Compress, Csv, Deque, Digest, Graph, Grid, Heap, Http, Ini, Json, Net, Regex, Rt, Set, Task, Toml, Unionfind, Xml, Yaml).

Conventions seen across these modules:
- Error types come in two shapes. A struct with a `kind` enum plus position: `JsonError`, `TomlError` (`kind, msg, line, col, path`), `RegexError` (`kind, pos`), `YamlError`, `XmlError`, `CsvError` (`kind, line, col`), `IniError` (`kind, line`). A bare enum (variants carry data): `HttpError`, `ChannelError`, `CompressError`, `ArchiveError`, `AddrParseError`, `GraphError`, `GridError`, `ParseBigIntError`. `std.net` uses `std.ioerror`'s `IoError`. All have `.message() -> str` and `impl Format` (so `f"{e}"` works); most derive `Eq` (`HttpError`, `CompressError`, `ArchiveError` compare by message because `IoError` has no `Eq`).
- Generic constructors need the type fixed from outside: `var s: set.Set<str> = set.new()` or `set.new<str>()`; a bare `let s = set.new()` is `cannot infer type parameter(s) T`.
- Default parameter values appear in signatures (`indent: int = 2`); trailing ones may be left out (D136).
- Struct literals of a module's type need `from std.m import T` (`regex.Match { … }` is a parse error); `m.Enum.Variant` works in an expression (`json.JsonErrorKind.Syntax`) but not as a pattern: in `match`, write the bare variant (`Syntax => …`).

## std.str (implicit): methods on `str`
Purpose: searching, splitting, trimming and case of byte strings. All are `impl str`. There are no `pub` functions.
- Search: `s.find(needle: str) -> Option<int>`, `s.rfind(needle: str) -> Option<int>`, `s.find_from(needle: str, start: int) -> Option<int>`, `s.contains(needle: str) -> bool`, `s.starts_with(prefix: str) -> bool`, `s.ends_with(suffix: str) -> bool`, `s.count(needle: str) -> int` (non-overlapping)
- Split: `s.split(sep: str) -> [str]`, `s.splitn(sep: str, n: int) -> [str]`, `s.words() -> [str]`, `s.lines() -> [str]`
- Trim: `s.trim() -> str`, `s.trim_start() -> str`, `s.trim_end() -> str`, `s.strip_prefix(p: str) -> Option<str>`, `s.strip_suffix(p: str) -> Option<str>`
- Transform: `s.to_upper() -> str`, `s.to_lower() -> str`, `s.repeat(n: int) -> str`, `s.pad_start(width: int, fill: char) -> str`, `s.pad_end(width: int, fill: char) -> str`, `s.replace(old: str, new: str) -> str`, `s.replacen(old: str, new: str, n: int) -> str`, `s.bytes() -> [uint8]` (one copy, for `w.write(s.bytes())`)
- Gotchas:
  - Positions are **byte** offsets (`"größe".find("ße")` is `Some(4)`).
  - `trim`, `words` and the case methods are ASCII only (`"Größe".to_upper()` is `"GRößE"`).
  - `pad_*` widths count characters.
  - `split("")` splits into one-character strings.
  - `lines()` drops `\n` and `\r\n`, and a final newline gives no empty last line.
  - An empty needle is found at 0, or at the end for `rfind`.
  - `repeat` past 2^31-1 bytes is a runtime error.
- Prose: `docs/Language/Standard-library/Str.md`

## std.char (implicit): methods on `char`
Purpose: ASCII classes and digits.
- `impl char`: `c.is_digit() -> bool`, `c.is_alpha() -> bool`, `c.is_alnum() -> bool`, `c.is_space() -> bool` (includes `\v`), `c.is_upper() -> bool`, `c.is_lower() -> bool`, `c.to_digit(radix: int) -> Option<int>`, `c.to_upper() -> char`, `c.to_lower() -> char`
- `pub fun from_digit(d: int, radix: int) -> Option<char>` (needs `import std.char as ch`)
- Gotchas: ASCII only (`'é'.is_alpha()` is false, and `to_upper` leaves it as it is). A radix outside 2..36 is a runtime error.
- Prose: `docs/Language/Standard-library/Char.md`

## std.int (implicit): methods on every integer width
Purpose: arithmetic helpers on `int8` to `int64` and `uint8` to `uint64`. The module is generated by `scripts/gen_std_int.py`, and each width has the same methods typed at its own width (`T` below).
- Basic: `x.abs() -> T` and `x.signum() -> T` (signed widths only), `x.min(o: T) -> T`, `x.max(o: T) -> T`, `x.clamp(lo: T, hi: T) -> T`, `x.pow(exp: uint32) -> T`, `x.gcd(o: T) -> T`, `x.lcm(o: T) -> T`, `x.div_euclid(o: T) -> T`, `x.rem_euclid(o: T) -> T`
- Bits: `x.count_ones() -> int`, `x.leading_zeros() -> int`, `x.trailing_zeros() -> int`
- Checked: `x.checked_add(o: T) -> Option<T>`, `checked_sub`, `checked_mul`, `checked_div`, `checked_rem`, `x.checked_neg() -> Option<T>`, `x.checked_abs() -> Option<T>`, `x.checked_pow(exp: uint32) -> Option<T>`. Unsigned widths have `checked_neg` too, but no `checked_abs`.
- Saturating: `x.saturating_add(o: T) -> T`, `saturating_sub`, `saturating_mul`, `x.saturating_pow(exp: uint32) -> T`
- Overflowing: `x.overflowing_add(o: T) -> (T, bool)`, `overflowing_sub`, `overflowing_mul`, `x.overflowing_neg() -> (T, bool)`, `x.overflowing_pow(exp: uint32) -> (T, bool)`, and `x.wrapping_pow(exp: uint32) -> T`
- Modular arithmetic: `x.mulmod(o: T, m: T) -> T`, `x.powmod(exp: T, m: T) -> T`, `x.modinv(m: T) -> Option<T>` (never overflows)
- Gotchas:
  - **`pow`'s exponent is `uint32`**: `2.pow(10)` works, but `2.pow(n)` with `n: int` is a type error. Write `n as uint32`.
  - `powmod`'s exponent has the receiver's type.
  - `pow`, `abs`, `gcd`, `lcm` and `div_euclid` overflow like the operators (a runtime error under run/test/`--checked`).
  - `wrapping_add`, `wrapping_sub`, `wrapping_mul` and `wrapping_neg` are builtins, not std.int methods.
  - `-5.abs()` parses as `-(5.abs())` and gives `-5`. Write `(-5).abs()`.
- Prose: `docs/Language/Standard-library/Int.md`

## std.float (implicit): methods on `float64` and `float32`
Purpose: the float operations as methods (D199, MYLA-585), over std.math. `impl float64` and `impl float32` with the same methods; a float32 one computes in float64 and rounds.
- Sign, rounding: `x.abs()`, `x.signum()` (a zero's sign too, NaN for NaN), `x.copysign(s)`, `x.trunc()`, `x.floor()`, `x.ceil()`, `x.round()` (halves away from zero), `x.fract()`
- Comparing: `x.min(o)`, `x.max(o)` (NaN gives way), `x.clamp(lo, hi)`, `x.total_cmp(o) -> int` (IEEE total order: `-0.0 < 0.0`, NaN last; `xs.sort_by((a, b) => a.total_cmp(b) < 0)`), `x.approx_eq(o, eps) -> bool`
- Powers: `x.sqrt()`, `x.cbrt()`, `x.hypot(o)`, `x.pow(y)`, `x.powi(n: int)`, `x.exp()`, `x.ln()`, `x.log2()`, `x.log10()`, `x.log(base)`
- Trigonometry: `x.sin()` … `x.atan()`, `y.atan2(x)`, `x.sinh()`, `x.cosh()`, `x.tanh()`, `x.to_degrees()`, `x.to_radians()`
- Other: `a.lerp(b, t)`, `x.is_nan()`, `x.is_infinite()`, `x.is_finite()`, `x.to_bits()` (`uint64`; a float32's `uint32`; every NaN the one quiet NaN)
- `import std.float as float` for: `PI`, `TAU`, `E`, `LN2`, `LN10`, `SQRT2`, `EPSILON`, `MAX`, `MIN_POSITIVE`, `nan()`, `infinity()`, `from_bits(b: uint64) -> float64`, `from_bits32(b: uint32) -> float32`. The alias `float` doesn't hide the type `float` where a type stands.
- Gotchas: `log(base)` and the hyperbolic functions are a few ulps off where their formulas aren't exact (`81.0.log(3.0)` is 4.000000000000001). A program's own method of one of these names on a float is a duplicate.
- Prose: `docs/Language/Standard-library/Float.md`

## std.list (implicit): methods on `[T]`
Purpose: building, higher-order operations, sorting, searching and combinatorics. A `var self` method changes the list in place (it needs a `var` place). A participle or a noun returns a new list.
- `pub fun filled<T>(n: int, v: T) -> [T]` (needs an import). `pub struct ListIter<T> { xs: [T], at: int }`, which has `impl<T> Iterator<T>`.
- `impl<T> [T]`, building:
  - Return a new list: `xs.reversed() -> [T]`, `xs.concat(o: [T]) -> [T]`
  - Change `xs` (`var self`): `xs.extend(o: [T])`, `xs.insert(i: int, v: T)`, `xs.remove_at(i: int) -> T`, `xs.swap(i: int, j: int)`, `xs.truncate(n: int)`
- `impl<T> [T]`, higher-order:
  - `xs.map<U>(f: (T) -> U) -> [U]`, `xs.filter(keep: (T) -> bool) -> [T]`, `xs.fold<A>(init: A, f: (A, T) -> A) -> A`, `xs.reduce(f: (T, T) -> T) -> Option<T>`
  - Predicates: `xs.any(p: (T) -> bool) -> bool`, `xs.all(p: (T) -> bool) -> bool`, `xs.find(p: (T) -> bool) -> Option<T>`, `xs.position(p: (T) -> bool) -> Option<int>`, `xs.count(p: (T) -> bool) -> int`
  - Extremes: `xs.min_by(less: (T, T) -> bool) -> Option<T>`, `xs.max_by(less: (T, T) -> bool) -> Option<T>`
  - Shape: `xs.flat_map<U>(f: (T) -> [U]) -> [U]`, `xs.zip<U>(o: [U]) -> [(T, U)]`, `xs.enumerate() -> [(int, T)]`, `xs.chunks(n: int) -> [[T]]`, `xs.windows(n: int) -> [[T]]`
- `impl<T> [T]`, sorting by a function (stable):
  - `xs.sort_by(less: (T, T) -> bool)` (in place), `xs.sorted_by(less: (T, T) -> bool) -> [T]`, `xs.sort_by_key<K: Ord>(key: (T) -> K)` (in place)
  - `xs.partition_point(p: (T) -> bool) -> int`
- `impl<T> [T]`, combinatorics: `xs.permutations() -> [[T]]`, `xs.combinations(k: int) -> [[T]]`. Iterating: `xs.iter() -> ListIter<T>`.
- `impl<T: Eq> [T]`: `xs.contains(v: T) -> bool`, `xs.index_of(v: T) -> Option<int>`, `xs.dedup()` (in place, removes adjacent repeats)
- `impl<T: Add> [T]`: `xs.sum(zero: T) -> T`. The zero is required: `xs.sum(0)`, `xs.sum(0.0)`.
- `impl<T: Ord> [T]`:
  - Sorting: `xs.sort()` (in place, stable merge sort), `xs.sorted() -> [T]`, `xs.sort_unstable()` (in place, introsort), `xs.is_sorted() -> bool`
  - Searching a sorted list: `xs.lower_bound(v: T) -> int`, `xs.upper_bound(v: T) -> int`, `xs.binary_search(v: T) -> Result<int, int>` (`Err` is the insertion point)
  - `xs.next_permutation() -> bool` (in place)
- `impl [str]`: `xs.join(sep: str) -> str`
- Gotchas:
  - There's no `min()` or `max()` on lists: use `min_by` or `max_by`, `iter.min(xs.iter())`, or `fold`.
  - `less` is "a goes before b", not a comparator returning an int.
  - `chunks` and `windows` with `n <= 0` are runtime errors.
  - `find` takes a predicate, and `index_of` takes a value.
- Prose: `docs/Language/Standard-library/List.md`

## std.option (implicit): methods on `Option<T>` and `Result<T, E>`
- `impl<T> Option<T>`:
  - `o.map<U>(f: (T) -> U) -> Option<U>`, `o.and_then<U>(f: (T) -> Option<U>) -> Option<U>`, `o.or_else(f: () -> Option<T>) -> Option<T>`
  - `o.unwrap_or(d: T) -> T`, `o.unwrap_or_else(f: () -> T) -> T`, `o.ok_or<E>(err: E) -> Result<T, E>`
  - `o.is_some() -> bool`, `o.is_none() -> bool`, `o.expect(msg: str) -> T` (panics with `msg`)
- `impl<T, E> Result<T, E>`:
  - `r.map<U>(f: (T) -> U) -> Result<U, E>`, `r.map_err<F>(f: (E) -> F) -> Result<T, F>`, `r.and_then<U>(f: (T) -> Result<U, E>) -> Result<U, E>`
  - `r.unwrap_or(d: T) -> T`, `r.ok() -> Option<T>`, `r.err() -> Option<E>`
  - `r.is_ok() -> bool`, `r.is_err() -> bool`, `r.expect(msg: str) -> T` (the panic message doesn't include the error)
- Gotchas: no `unwrap`, `unwrap_err`, `filter`, `ok_or_else`, `Result.or_else` or `Result.unwrap_or_else`.
- Prose: `docs/Language/Standard-library/Option.md`

## std.map (implicit): methods on `[K: V]`
- `impl<K: Eq + Hash, V> [K: V]`:
  - Read: `m.get(k: K) -> Option<V>`, `m.get_or(k: K, d: V) -> V`
  - Change (`var self`): `m.update(k: K, d: V, f: (V) -> V)`, `m.merge(o: [K: V])` (`o` wins)
  - List: `m.values() -> [V]`, `m.items() -> [(K, V)]`, `m.iter() -> ListIter<(K, V)>`
- `pub fun counts<T: Eq + Hash>(xs: [T]) -> [T: int]` (needs `import std.map as map_m`)
- Gotchas:
  - `contains`, `keys` and `remove` are builtins, and `remove` returns `()`.
  - Reading `m[k]` for a missing key is a runtime error.
  - Every order is insertion order.
- Prose: `docs/Language/Standard-library/Map.md`

## std.hash (implicit): `Hasher` methods, `Hash` impls, wyhash
- `Hasher { state: uint64 }` is the **prelude's** struct, so a literal works without an import. `trait Hash { fun hash(self, h: Hasher) -> Hasher }` is also the prelude's.
- `impl Hasher`, each method returning `Hasher`:
  - `h.add<T: Hash>(x: T)`, `h.add_str(s: str)`, `h.add_bytes(b: [uint8])`, `h.add_bool(x: bool)`, `h.add_char(x: char)`
  - Integers: `h.add_u8(x)`, `h.add_u16(x)`, `h.add_u32(x)`, `h.add_u64(x)`, `h.add_i8(x)`, `h.add_i16(x)`, `h.add_i32(x)`, `h.add_i64(x)`
  - `h.finish() -> uint64`
- `impl Hash for` every integer type, `float64`, `float32` (D198: the value's float64 bits, `-0.0` as `0.0`; a NaN panics `cannot hash NaN`), `char`, `bool`, `str` and `[T: Hash]`. A list adds its length first. Tuples are hashed by the language.
- `pub fun new() -> Hasher`, `pub fun with_seed(seed: uint64) -> Hasher`, `pub fun wyhash(s: str, seed: uint64) -> uint64`, `pub fun wyhash_bytes(b: [uint8], seed: uint64) -> uint64`. These need `import std.hash as hash`.
- Gotchas:
  - The hasher is a value: write `h = h.add_u64(x)` or chain the calls.
  - The seed is fixed, so hashes are the same in every run.
  - The checksums (FNV, CRC-32) are in `std.checksum`.
- Prose: `docs/Language/Standard-library/Hash.md`

---

## std.archive
tar (ustar + pax/GNU read; pax written) read/write; zip read only (stored + deflate, CRC checked; ZIP64/encryption are errors). `import std.archive as archive`.
- `enum ArchiveError { Truncated, BadHeader, BadName, NotZip, Zip64, Encrypted, Unsupported(int32), ChecksumMismatch, LengthMismatch, Compress(CompressError), TooLarge, UnsafeName, Io(IoError) }`
- `enum EntryKind { File, Dir, Symlink, Hardlink, Other(uint8) }`
- `struct Entry { name: str, kind: EntryKind, mode: int32, mtime: int64, uid: int64, gid: int64, uname: str, gname: str, link: str, data: [uint8] }`
- `fun file(name: str, data: [uint8]) -> Entry` · `fun dir(name: str) -> Entry` · `fun symlink(name: str, target: str) -> Entry`
- `fun is_safe_name(name: str) -> bool` · `fun safe_path(dir: str, name: str) -> Result<str, ArchiveError>` (`UnsafeName` for `..`, absolute, …)
- `fun tar_write(entries: [Entry]) -> Result<[uint8], ArchiveError>` · `fun tar_read(b: [uint8]) -> Result<[Entry], ArchiveError>`
- `fun tar_writer<W: Write>(w: W) -> TarWriter<W>`: `.add(var self, e: Entry) -> Result<(), ArchiveError>`, `.finish(self) -> Result<W, ArchiveError>`
- `fun tar_reader<R: Read>(r: R) -> TarReader<R>`: `.next_entry(var self) -> Result<Option<Entry>, ArchiveError>`; it is an `Iterator<Result<Entry, ArchiveError>>`
- `struct ZipFile { name, kind, mode: int32, mtime: int64, method: int32, flags: int32, crc: uint32, csize: int64, size: int64, offset: int64, … }`
- `fun zip_list(b: [uint8]) -> Result<[ZipFile], ArchiveError>` · `fun zip_data(b: [uint8], f: ZipFile, max_output: int = 0x7FFFFFFF) -> Result<[uint8], ArchiveError>` · `fun zip_read(b: [uint8], max_output: int = 0x7FFFFFFF) -> Result<[Entry], ArchiveError>`

## std.algebra: `Zero`, `One`, `Identity`
Purpose: the traits of distinguished values (D201): `trait Zero { fun zero() -> Self }`, `trait One { fun one() -> Self }`, `trait Identity { fun identity() -> Self }`, called on a type (`int.zero()`, `Vec3.zero()`, `Mat4.identity()`, `T.zero()` under a bound). Every integer and float type implements `Zero` and `One` here.
- `pub fun sum<T: Add + Zero>(xs: [T]) -> T`, `pub fun product<T: Mul + One>(xs: [T]) -> T`
- Gotchas: importing it (or std.vector/matrix/quaternion, which do) makes `zero`/`one` the number types' methods: a program's own `impl Zero for int` of another trait is then a duplicate method. `#test` can't sit on a generic function (its cases are a test function with `assert`).
- Prose: `docs/Language/Standard-library/Algebra.md`

## std.args: command-line parsing (getopt and GNU forms)
Import: `import std.args as args`.
- `pub enum ArgsError { Help(str), UnknownOption(str), MissingValue(str), UnexpectedValue(str), MissingPositional(str), UnexpectedPositional(str), UnknownCommand(str) }` is `Eq`, with `e.message() -> str` and `Format`.
- `pub struct Spec`, `pub struct Args` (opaque fields)
- Building a spec: `pub fun spec(name: str, about: str = "") -> Spec`. Each `Spec` method returns a new `Spec`:
  - `s.flag(name: str, short: char = '\0', help: str = "")`
  - `s.option(name: str, short: char = '\0', value: str = "VALUE", help: str = "", default: Option<str> = None)`
  - `s.positional(name: str, help: str = "", required: bool = true)`, `s.many(name: str, help: str = "")`, `s.command(name: str, sub: Spec)`
  - Output: `s.usage() -> str`, `s.help() -> str`. `check_name` and `check_option` are internal.
- Parsing: `pub fun parse(s: Spec, argv: [str]) -> Result<Args, ArgsError>`, `pub fun parse_or_exit(s: Spec, argv: [str]) -> Args` (prints help and exits 0, or exits 2 on an error)
- `impl Args`: `a.flag(name: str) -> bool`, `a.count(name: str) -> int`, `a.get(name: str) -> Option<str>`, `a.get_or(name: str, d: str) -> str`, `a.all(name: str) -> [str]`, `a.command() -> Option<(str, Args)>`
- Gotchas:
  - `argv` excludes the program name: pass `process.args()[1:]`.
  - `--help` and `-h` come back as `Err(ArgsError.Help(text))`.
  - Asking for an undeclared name panics, and so does a bad spec.
  - Values are always `str`.
- Prose: `docs/Language/Standard-library/Args.md`

## std.bench: time a closure
Import: `import std.bench as bench`.
- `pub struct Report { name: str, runs: int, batch: int, times: [float64], min: float64, median: float64, max: float64, spread: float64 }`, with `r.line() -> str` and `Format`. Times are nanoseconds per call.
- `pub fun run<T>(name: str, f: () -> T) -> Report` (about 1 s, 5 to 1000 runs)
- `pub fun run_n<T>(name: str, n: int, f: () -> T) -> Report`
- `pub fun run_for<T>(name: str, budget: time.Duration, f: () -> T) -> Report`
- `pub fun black_box<T>(v: T) -> T`, `pub fun summary(name: str, batch: int, totals: [int64]) -> Report`, `pub fun duration_text(ns: float64) -> str`
- Prose: `docs/Language/Standard-library/Bench.md`

## std.bigint
Arbitrary-precision integers (Karatsuba, Burnikel-Ziegler). `import std.bigint as bigint`.
- `#derive(Eq, Hash) struct BigInt` (opaque; a map key) · `enum ParseBigIntError { Empty, InvalidDigit(int) }`
- `fun zero() -> BigInt` · `fun from_int(n: int64) -> BigInt` · `fun from_uint(n: uint64) -> BigInt` · `fun parse(s: str) -> Result<BigInt, ParseBigIntError>` · `fun parse_radix(s: str, radix: int) -> Result<BigInt, ParseBigIntError>` (radix outside 2..36: runtime error)
- Operators `+ - * / %` (truncating), `== < <= > >=` (`Ord`), `f"{x}"` (`Format`: width/alignment only, a precision is a runtime error).
- Methods: `.is_zero()`, `.is_negative()`, `.signum() -> int`, `.neg()`, `.abs()`, `.pow(exp: uint32)`, `.div_rem(o) -> (BigInt, BigInt)`, `.div_floor(o)`, `.mod_floor(o)`, `.div_euclid(o)`, `.rem_euclid(o)`, `.shl(n: int)`, `.shr(n: int)`, `.bit_len() -> int`, `.to_int64() -> Option<int64>`, `.to_uint64() -> Option<uint64>`, `.to_str_radix(radix: int) -> str`
- Gotcha: no unary minus (`-x` is `unary '-' requires a numeric operand`): use `x.neg()`. Mixed `BigInt + int` doesn't exist: wrap with `bigint.from_int(n)`.

## std.bitset
Sets of small non-negative ints, a bit each. `import std.bitset as bitset`.
- `#derive(Eq, Hash) struct BitSet` · `fun new() -> BitSet` (growable) · `fun fixed(n: int) -> BitSet` (0..n-1; inserting outside is a failure) · `fun of(xs: [int]) -> BitSet`
- `.insert(var self, i: int) -> bool`, `.remove(var self, i) -> bool`, `.toggle(var self, i) -> bool`, `.contains(i) -> bool`, `.popcount() -> int`, `.is_empty()`, `.capacity() -> int`, `.cleared() -> BitSet`, `.items() -> [int]`, `.next_from(i: int) -> Option<int>`, `.union(o)`, `.intersection(o)`, `.difference(o)`, `.symmetric_difference(o)`, `.complemented()` (fixed sets), `.is_subset(o) -> bool`, `.is_disjoint(o) -> bool`

## std.btree
Sorted map and set (B+ tree in an arena; O(log n)). `import std.btree as btree`.
- `struct SortedMap<K, V>` (`K: Ord`) · `fun new<K: Ord, V>() -> SortedMap<K, V>` · `fun of<K: Ord, V>(pairs: [(K, V)]) -> SortedMap<K, V>`
  - `.insert(var self, k: K, v: V) -> Option<V>` (old value) · `.get(k) -> Option<V>` · `.contains(k) -> bool` · `.remove(var self, k) -> Option<V>` · `.len() -> int` · `.is_empty() -> bool`
  - `.first() -> Option<(K, V)>` · `.last()` · `.floor(k) -> Option<(K, V)>` (greatest ≤ k) · `.ceiling(k)` (least ≥ k) · `.range(lo: K, hi: K) -> [(K, V)]` (lo inclusive, hi exclusive)
  - `.keys() -> [K]` · `.values() -> [V]` · `.items() -> [(K, V)]` · `.iter() -> SortedMapIter<K, V>` (`Iterator<(K, V)>`) · `.pop_first(var self) -> Option<(K, V)>` · `.pop_last(var self)`
- `struct SortedSet<T>` · `fun set_new<T: Ord>() -> SortedSet<T>` · `fun set_of<T: Ord>(xs: [T]) -> SortedSet<T>`
  - `.insert(var self, x) -> bool` · `.remove(var self, x) -> bool` · `.contains(x)` · `.len()` · `.is_empty()` · `.first() -> Option<T>` · `.last()` · `.floor(x)` · `.ceiling(x)` · `.range(lo, hi) -> [T]` · `.items() -> [T]` · `.iter() -> SortedSetIter<T>` · `.pop_first(var self) -> Option<T>` · `.pop_last(var self)` · `.union(o)` · `.intersection(o)` · `.difference(o)` · `.is_subset(o) -> bool`
- Gotcha: the set constructors are `set_new`/`set_of`, not `new`/`of`. Not `Eq`-comparable with `==` (no impl).

## std.bytes: `[uint8]` and `str` conversion, UTF-8
Import: `import std.bytes as bytes`.
- `pub fun from_str(s: str) -> [uint8]` (same as `s.bytes()`), `pub fun to_str(b: [uint8]) -> str` (no UTF-8 check)
- `pub fun is_utf8(b: [uint8]) -> bool`, `pub fun utf8_error(b: [uint8]) -> Option<int>`
- `pub fun encode_char(c: char) -> [uint8]`, `pub fun decode_char(b: [uint8], at: int) -> Option<(char, int)>`
- Prose: `docs/Language/Standard-library/Bytes.md`

## std.cache
LRU cache and memoising. `import std.cache as cache`.
- `struct Lru<K, V>` (`K: Eq + Hash`) · `fun new<K: Eq + Hash, V>(capacity: int) -> Lru<K, V>` (capacity < 1 keeps nothing)
  - `.len()` · `.is_empty()` · `.capacity() -> int` · `.contains(k) -> bool` (no use) · `.get(var self, k) -> Option<V>` (marks it used: needs `var`) · `.peek(k) -> Option<V>` (no use) · `.put(var self, k, v) -> Option<(K, V)>` (the evicted entry) · `.remove(var self, k) -> Option<V>` · `.clear(var self)` · `.keys() -> [K]` · `.items() -> [(K, V)]` (most recent first)
- `struct Memo<K, V>` · `fun new_memo<K: Eq + Hash, V>(f: (K) -> V) -> Memo<K, V>` · `fun recursive<K: Eq + Hash, V>(step: (K, [K: V]) -> Result<V, K>) -> Memo<K, V>`
  - `.get(var self, k) -> V` · `.peek(k) -> Option<V>` · `.contains(k) -> bool` · `.set(var self, k, v)` · `.len()` · `.clear(var self)`
- Gotcha: a `recursive` step returns `Err(j)` for a key it needs first (a closure can't call the memo it is in); a cycle is a failure. Annotate the variable, `var fib: cache.Memo<int, int64> = cache.recursive((n: int, known: [int: int64]) => { … })`, or the step's `Ok(…)` can't infer its error type.

## std.checksum
FNV-1a, CRC-32 (IEEE), Adler-32; every function has a `str` form and a `_bytes` (`[uint8]`) form. `import std.checksum as checksum`.
- `fun fnv1a32(s: str) -> uint32` · `fnv1a32_bytes(b: [uint8]) -> uint32` · `fnv1a64(s) -> uint64` · `fnv1a64_bytes(b) -> uint64`
- `fun crc32(s: str) -> uint32` · `crc32_bytes(b)` · `crc32_update(crc: uint32, s: str) -> uint32` · `crc32_update_bytes(crc: uint32, b: [uint8]) -> uint32`
- `fun adler32(s) -> uint32` · `adler32_bytes(b)` · `adler32_update(adler: uint32, s)` · `adler32_update_bytes(adler: uint32, bytes: [uint8])`
- Gotcha: these used to be `std.hash`'s (D166); now an explicit import. `std.hash` is only the `Hasher`.

## std.compress
DEFLATE (RFC 1951) inflate and deflate; gzip and zlib containers; as functions and as streams. `import std.compress as compress`.
- `enum CompressError { Truncated, BadHeader, PresetDictionary, BadBlockType, BadStoredLength, BadCodeLengths, BadCode, DistanceTooFar, ChecksumMismatch, LengthMismatch, TrailingData, TooLarge, Io(IoError) }`
- `fun inflate(b: [uint8], max_output: int = 0x7FFFFFFF) -> Result<[uint8], CompressError>` · `gunzip(b, max_output = …)` · `zlib_decompress(b, max_output = …)` (past `max_output`: `TooLarge`)
- `fun deflate(b: [uint8], level: int = 6) -> [uint8]` · `gzip(b, level = 6)` · `zlib_compress(b, level = 6)` (never fail)
- Streams: `fun inflate_reader<R: Read>(r: R) -> Decoder<R>`, `gzip_reader`, `zlib_reader` (`Decoder` is a `Read`; a corrupt stream reads as `IoError.InvalidInput`, `.error() -> Option<CompressError>` says why). `fun deflate_writer<W: Write>(w: W, level: int = 6) -> Encoder<W>`, `gzip_writer`, `zlib_writer` (`Encoder` is a `Write`; `.finish(self) -> Result<W, IoError>` must be called, nothing finishes it at exit).
- Gotcha: works on `[uint8]`, not `str`: `bytes.from_str(s)` / `bytes.to_str(b)` from `std.bytes`.

## std.csv
RFC 4180 CSV (Go/Python-strict semantics). `import std.csv as csv`.
- `enum CsvErrorKind { BareQuote, UnclosedQuote, AfterQuote, FieldCount, DuplicateName, Io }` · `struct CsvError { kind, line: int, col: int }` (`f"{e}"` = `line:col: msg`)
- `fun parse(text: str) -> Result<[[str]], CsvError>` · `fun parse_with(text: str, delim: char) -> Result<[[str]], CsvError>`
- `fun parse_records(text: str) -> Result<[[str: str]], CsvError>` (first row is the header; each row a map) · `fun parse_records_with(text, delim: char)`
- `fun stream_reader<R: Read>(r: R) -> CsvStreamReader<R>` · `stream_reader_with(r, delim: char)`: `.read_record(var self) -> Result<Option<[str]>, CsvError>`, `.io_error() -> Option<IoError>`; an `Iterator<Result<[str], CsvError>>`
- `fun write(rows: [[str]]) -> str` · `fun write_with(rows: [[str]], delim: char, line_end: str = "\r\n") -> str`
- Gotcha: `write` ends records with CRLF; a blank line is no record; records may differ in length (except under `parse_records`).

## std.deque
Ring-buffer double-ended queue (also the FIFO queue). `import std.deque as deque`.
- `struct Deque<T>` · `fun new<T>() -> Deque<T>` · `fun with_capacity<T>(n: int) -> Deque<T>` · `fun of<T>(xs: [T]) -> Deque<T>`
- `.len() -> int` · `.is_empty() -> bool` · `.push_back(var self, v: T)` · `.push_front(var self, v: T)` · `.pop_back(var self) -> Option<T>` · `.pop_front(var self) -> Option<T>` · `.front() -> Option<T>` · `.back() -> Option<T>` · `.get(i: int) -> Option<T>` · `.set(var self, i: int, v: T)` (out of bounds: failure) · `.iter() -> DequeIter<T>` (`Iterator<T>`, front to back) · `.items() -> [T]`
- Gotcha: `pop_front()` is an `Option`: `print(q.pop_front())` doesn't type-check; no `d[i]` indexing (use `get`/`set`).

## std.digest
MD5, SHA-1, SHA-224/256, SHA-384/512, HMAC. `import std.digest as digest`.
- `trait Digest { fun update(var self, data: [uint8]); fun finish(self) -> [uint8]; fun block_size(self) -> int }`
- Types `Md5`, `Sha1`, `Sha256` (also 224), `Sha512` (also 384): `fun new_md5()`, `new_sha1()`, `new_sha256()`, `new_sha224()`, `new_sha512()`, `new_sha384()`; methods `.update(var self, data: [uint8])`, `.update_str(var self, s: str)`, `.finish(self) -> [uint8]`, `.finish_hex(self) -> str`, `.block_size()`
- One-shot: `fun md5(data: [uint8]) -> [uint8]`, `md5_hex(s: str) -> str`; same for `sha1`, `sha256`, `sha224`, `sha512`, `sha384` (`_hex` takes a `str`, the plain form `[uint8]`)
- HMAC: `fun hmac<D: Digest>(d: D, key: [uint8], msg: [uint8]) -> [uint8]` (`hmac(digest.new_sha256(), k, m)`); `hmac_md5(key: [uint8], msg: [uint8])`, `hmac_md5_hex(key: str, msg: str) -> str`, and `hmac_sha1`, `hmac_sha256`, `hmac_sha512` with `_hex` twins.

## std.encoding: hex and Base64
Import: `import std.encoding as encoding`.
- `pub enum EncodingError { BadLength(int), BadChar(int), BadPadding(int), TrailingBits(int) }` is `Eq`, with `message()` and `Format`. The payload is a byte position.
- `pub fun hex_encode(b: [uint8]) -> str`, `pub fun hex_decode(s: str) -> Result<[uint8], EncodingError>`
- `pub fun base64_encode(b: [uint8]) -> str`, `pub fun base64_decode(s: str) -> Result<[uint8], EncodingError>` (padding required)
- `pub fun base64_url_encode(b: [uint8], pad: bool = true) -> str`, `pub fun base64_url_decode(s: str) -> Result<[uint8], EncodingError>`
- Gotcha: everything works on bytes. Use `s.bytes()` and `bytes.to_str(…)` to get there and back.
- Prose: `docs/Language/Standard-library/Encoding.md`

## std.fmt: format specs (used by the checker and runtime)
Import: `import std.fmt as fmt`.
- `pub struct Spec { fill: str, align: uint8, plus: bool, alt: bool, zero: bool, width: int32, prec: int32, kind: uint8 }`
- For users: `pub fun pad(text: str, spec: str) -> str` gives the fill, alignment and width of `spec` inside your own `impl Format { fun format(self, spec: str) -> str }`. An invalid spec is a runtime error.
- Internal: `parse_spec(s: str) -> Result<Spec, str>`, `spec_need(sp: Spec, class: int32) -> str`, `fmt_int(v: int64, bits: int32, signed: bool, spec: str) -> str`, `fmt_float(x: float64, text: str, spec: str) -> str`, `fmt_text(text: str, spec: str) -> str`
- Prose: `docs/Language/Standard-library/Fmt.md`

## std.fs: files, directories, metadata, temporary files
Import: `import std.fs as fs`. `IoError`, `from_errno` and `io_error_name` are re-exported from std.ioerror, so `fs.IoError` and `from std.fs import IoError` work.
- Whole files:
  - `pub fun read_to_string(path: str) -> Result<str, IoError>`, `pub fun write_to_file(path: str, contents: str) -> Result<(), IoError>` (creates or truncates, mode 0644)
  - `pub fun read_bytes(path: str) -> Result<[uint8], IoError>`, `pub fun write_bytes(path: str, b: [uint8]) -> Result<(), IoError>`
- Directories:
  - `pub fun current_dir() -> Result<str, IoError>`, `pub fun list_dir(path: str) -> Result<[str], IoError>` (names only, sorted by bytes, no `.` or `..`)
  - `pub fun make_dir(path: str) -> Result<(), IoError>`, `pub fun make_dir_all(path: str) -> Result<(), IoError>`
  - `pub fun remove_file(path: str) -> Result<(), IoError>`, `pub fun remove_dir(path: str) -> Result<(), IoError>` (the directory must be empty), `pub fun remove_dir_all(path: str) -> Result<(), IoError>`
  - `pub fun rename(from_path: str, to: str) -> Result<(), IoError>`
- Tests: `pub fun exists(path: str) -> bool`, `pub fun is_dir(path: str) -> bool`, `pub fun is_file(path: str) -> bool`, `pub fun is_symlink(path: str) -> bool`. These return bools, not `Result`s.
- Metadata:
  - `pub fun metadata(path: str) -> Result<Metadata, IoError>` follows links. `pub fun symlink_metadata(path: str) -> Result<Metadata, IoError>` doesn't.
  - `pub struct Metadata { size: int64, kind: FileKind, permissions: int32, modified_ns: int64 }` is `Eq`, with `md.is_file() -> bool`, `md.is_dir() -> bool` and `md.is_symlink() -> bool`.
  - `pub enum FileKind { File, Dir, CharDevice, BlockDevice, Fifo, Socket, Symlink, Other }` is `Eq`.
- Streams:
  - `pub struct File { fd: int32 }` implements `io.Read`, `io.Write`, `io.Seek` and `io.Pollable`.
  - Opening: `pub fun open(path: str) -> Result<File, IoError>` (read), `pub fun create(path: str) -> Result<File, IoError>` (write, truncate), `pub fun open_append(path: str) -> Result<File, IoError>`
  - `impl File`: `f.len() -> Result<int64, IoError>`, `f.metadata() -> Result<Metadata, IoError>`, `f.close() -> Result<(), IoError>` (`var self`)
  - Also on a `File`, from the traits: `f.read(n: int) -> Result<[uint8], IoError>`, `f.write(b: [uint8]) -> Result<int, IoError>`, `f.flush()`, `f.seek(pos: io.SeekFrom) -> Result<int64, IoError>`, `f.descriptor() -> int32`
- Open options:
  - `pub fun options() -> OpenOptions`, where `pub struct OpenOptions` is `Eq`.
  - Each method returns a new `OpenOptions`: `.read(on: bool)`, `.write(on: bool)`, `.append(on: bool)`, `.truncate(on: bool)`, `.create(on: bool)`, `.create_new(on: bool)`, `.mode(perms: int32)`
  - Finally `.open(path: str) -> Result<File, IoError>`. Options that choose nothing give `InvalidInput`.
- Temporary files:
  - `pub fun temp_root() -> str` (`$TMPDIR` or `/tmp`)
  - `pub fun make_temp_dir() -> Result<str, IoError>`, `pub fun make_temp_dir_in(dir: str, prefix: str) -> Result<str, IoError>`
  - `pub fun make_temp_file() -> Result<(str, File), IoError>`, `pub fun make_temp_file_in(dir: str, prefix: str) -> Result<(str, File), IoError>`
- Gotchas:
  - `File` is unbuffered, so wrap it in `io.buffered(f)` or `io.buffered_writer(f)`.
  - There is no destructor: `defer { let c = f.close() }`.
  - A copy of a `File` shares its descriptor, and `close` closes it for all copies (later use gives `Other(9)`).
  - `make_temp_file` returns a **tuple** with an open file.
  - Ignored `Result`s must be bound (`let r = fs.remove_dir_all(d)`).
- Prose: `docs/Language/Standard-library/Fs.md`

## std.glob: glob patterns and directory walks
Import: `import std.glob as glob`. Syntax: `*`, `?`, `[a-z]`, `[!…]`, `\`, and `**` as a whole component. A leading `.` must be matched literally.
- `pub struct Pattern` (opaque). `pub fun compile(pattern: str) -> Pattern`, then `p.matches(path: str) -> bool`. Or in one step: `pub fun matches(pattern: str, p: str) -> bool`.
- `pub fun walk(dir: str) -> Result<[str], IoError>` (sorted and relative, links not followed), `pub fun walk_with(dir: str, follow_links: bool) -> Result<[str], IoError>`
- `pub fun glob(pattern: str) -> Result<[str], IoError>`, `pub fun glob_in(dir: str, pattern: str) -> Result<[str], IoError>`
- Prose: `docs/Language/Standard-library/Glob.md`

## std.graph
Searches over a neighbour function (no stored graph). `import std.graph as graph`. Nodes: any `T: Eq + Hash`; weights `int64`, never negative (a negative weight or overflow is a failure).
- `struct Path<T> { nodes: [T], cost: int64 }` · `enum GraphError { Cycle }`
- `fun bfs<T: Eq + Hash>(start: T, next: (T) -> [T]) -> [T: int]` (distances, in visiting order)
- `fun bfs_path<T: Eq + Hash>(start: T, goal: (T) -> bool, next: (T) -> [T]) -> Option<Path<T>>`
- `fun dfs<T: Eq + Hash>(start: T, next: (T) -> [T]) -> [T]` (preorder)
- `fun dijkstra<T: Eq + Hash>(start: T, next: (T) -> [(T, int64)]) -> [T: int64]`
- `fun dijkstra_path<T: Eq + Hash>(start: T, goal: (T) -> bool, next: (T) -> [(T, int64)]) -> Option<Path<T>>`
- `fun astar<T: Eq + Hash>(start: T, goal: (T) -> bool, next: (T) -> [(T, int64)], h: (T) -> int64) -> Option<Path<T>>`
- `fun topo_sort<T: Eq + Hash>(nodes: [T], next: (T) -> [T]) -> Result<[T], GraphError>` · `fun components<T: Eq + Hash>(nodes: [T], next: (T) -> [T]) -> [[T]]`
- Dense (nodes 0..n-1, 4-10x faster; `-1` = unreached): `fun bfs_dense(n: int, start: int, next: (int) -> [int]) -> [int]` · `fun dijkstra_dense(n: int, start: int, next: (int) -> [(int, int64)]) -> [int64]`
- Gotcha: edge weights are `int64`: write `1i64` in the neighbour lambda.

## std.grid
2-D grid, positions are `(x, y)` tuples (`y` down). `import std.grid as grid`.
- `#derive(Eq, Hash) struct Grid<T> { width: int, height: int, cells: [T] }` · `enum GridError { Ragged(int, int, int) }`
- `fun new<T>(width: int, height: int, fill: T) -> Grid<T>` · `fun of<T>(rows: [[T]]) -> Result<Grid<T>, GridError>` · `fun parse(text: str) -> Result<Grid<char>, GridError>` · `fun parse_with<T>(text: str, f: (char) -> T) -> Result<Grid<T>, GridError>`
- `.in_bounds(p: (int, int)) -> bool` · `.at(p) -> Option<T>` · `.set(var self, p, v: T)` · `.neighbours4(p) -> [(int, int)]` · `.neighbours8(p)` · `.index(p) -> int` · `.pos(i: int) -> (int, int)` · `.positions() -> [(int, int)]` · `.row(y: int) -> [T]` · `.column(x: int) -> [T]` · `.map<U>(f: (T) -> U) -> Grid<U>` · `.transposed() -> Grid<T>`
- With `T: Eq`: `.find(v: T) -> Option<(int, int)>`, `.find_all(v) -> [(int, int)]`. With `T: Format`: `.text() -> str` (no trailing newline).

## std.heap
Binary heaps. `import std.heap as heap`.
- `struct Heap<T>` (`T: Ord`, least first unless max) · `fun new<T: Ord>() -> Heap<T>` · `fun max_new<T: Ord>() -> Heap<T>` · `fun of<T: Ord>(xs: [T]) -> Heap<T>` (O(n)) · `fun max_of<T: Ord>(xs: [T]) -> Heap<T>`
  - `.len()` · `.is_empty()` · `.push(var self, x: T)` · `.pop(var self) -> Option<T>` · `.peek() -> Option<T>` · `.iter() -> HeapIter<T>` (pops a copy, in pop order; `Iterator<T>`) · `.into_sorted(self) -> [T]` (pop order)
- `struct KeyedHeap<T>` (any `T`, `int64` priority, least first) · `fun keyed_new<T>() -> KeyedHeap<T>`
  - `.len()` · `.is_empty()` · `.push(var self, priority: int64, value: T)` · `.pop(var self) -> Option<(int64, T)>` · `.peek() -> Option<(int64, T)>`
- Gotcha: no `Reverse<T>`: use `max_new`/`max_of`. A struct element needs `impl Ord for J { fun cmp(self, other: J) -> int }`.

## std.http
HTTP/1.1 client and server over std.net, plain HTTP only (`https` → `Unsupported("https")`; wasm32 → `Unsupported("sockets")`). `import std.http as http` (struct literals or handler types: `from std.http import Request, Response`).
- `enum HttpError { InvalidUrl(str), Unsupported(str), Io(IoError), TimedOut, Closed, Truncated, BadStartLine, BadHeader, BadLength, BadChunk, HeadersTooLarge, BodyTooLarge, TooManyRedirects, Decode(CompressError) }` (`Eq` by message, `Format`)
- `#derive(Eq) struct Headers { items: [(str, str)] }` · `fun headers() -> Headers`: `.get(name) -> Option<str>` (case-insensitive, first) · `.get_all(name) -> [str]` · `.has(name) -> bool` · `.has_token(name, token) -> bool` · `.add(var self, name, value)` · `.set(var self, name, value)` (replaces) · `.remove(var self, name)` · `.len() -> int`
- `fun reason(status: int) -> str` (standard phrase, "" if unknown)
- `struct Request { method: str, url: str, version: str, headers: Headers, body: str, trailers: Headers, peer: Option<SocketAddr>, timeout_ms: int, max_redirects: int, decompress: bool, max_header_bytes: int, max_body_bytes: int, params: [(str, str)] }`
  - `fun request(method: str, url: str) -> Request` (no time limit, 5 redirects, gzip/deflate asked and decoded)
  - builders: `.with_header(name, value)`, `.with_body(body: str)`, `.with_timeout(ms: int)`, `.with_redirects(n: int)`, `.with_decompress(on: bool)`, `.with_limits(header_bytes: int, body_bytes: int)`, each `-> Request`
  - `.header(name) -> Option<str>` · `.path() -> str` (no query; "/" if none) · `.query() -> [(str, str)]` (decoded) · `.text() -> str` (lossy UTF-8) · `.bytes() -> [uint8]`
  - `.query_param(name) -> Option<str>` (first, decoded) · `.param(name) -> Option<str>` / `.param_int(name) -> Option<int>` (path parameters a router matched)
- `struct Response { status: int, reason: str, version: str, headers: Headers, body: str, trailers: Headers, url: str }`
  - `fun response(status: int, body: str) -> Response` · `.with_header(name, value) -> Response` · `.with_trailer(name, value) -> Response` (sent chunked) · `.header(name) -> Option<str>` · `.is_success() -> bool` (200..299) · `.text() -> str` · `.bytes() -> [uint8]`
- Client, one connection each (sync / **async**): `fun send(r: Request) -> Result<Response, HttpError>` / `async fun send_async(r)`; `fun get(url: str)` = `fun fetch(url: str)` / `async fun get_async(url)` = `async fun fetch_async(url)`; `fun post(url: str, body: str)` / `async fun post_async(url, body)`; all `-> Result<Response, HttpError>`.
- Keep-alive client: `struct Client` · `fun client() -> Client`: `.send(var self, r)`, `async .send_async(var self, r)`, `.get(var self, url)`, `.post(var self, url, body)`, `async .get_async(var self, url)`, `async .post_async(var self, url, body)`, `.close(var self)`.
- Server (all **async**): `struct ServerOptions { workers: int, max_connections: int, max_requests: int, max_header_bytes: int, max_body_bytes: int, keep_alive_ms: int, idle_ms: int, read_ms: int, write_ms: int }` · `fun server_options() -> ServerOptions` (64 workers, 1024 conns, no request limit, 64 KiB head, 16 MiB body, 60 s / 5 s / 20 s / 30 s)
  - `async fun serve(addr: SocketAddr, handler: (Request) -> Response) -> Result<(), HttpError>` (until cancelled)
  - `async fun serve_n(l: TcpListener, n: int, handler: (Request) -> Response) -> Result<int, HttpError>` (n requests, then returns; for tests)
  - `async fun serve_with(l: TcpListener, o: ServerOptions, handler: async (Request) -> Response) -> Result<int, HttpError>` (async handler; stops at `max_requests` or when cancelled)
- Router (D202, sync handlers): `fun router(base: str) -> Router` · `.route(var self, method, path, handler)` (method `"*"` = any; same method+pattern replaces) · `.get/.post/.put/.patch/.delete(var self, path, handler)` · `.mount(var self, sub: Router)` (sub at its own base below this one; copied when mounted) · `.static_files(var self, prefix, dir)` (GET; `..` → 404; `fun content_type(name) -> str`) · `.wrap(var self, mw: ((Request) -> Response) -> (Request) -> Response)` (first added = outermost) · `.handler(self) -> (Request) -> Response` (snapshot: pass to `serve`) · `.dispatch(self, req) -> Response` (no middleware)
  - Patterns: literal, `{name}`, `{name:int}`, last `{name:path}` (rest, maybe empty). Most specific wins regardless of order (literal 3, int 2, param 1, path 0; ties: first added). GET answers HEAD. Other method only → 405 + `Allow`; else 404 `not found`.
  - Typed endpoints: `fun json<O: json.ToJson>(f: (Request) -> Result<O, Response>) -> (Request) -> Response` · `fun json_body<I: json.FromJson, O: json.ToJson>(f: (Request, I) -> Result<O, Response>) -> (Request) -> Response` (bad body → 422 `{"error": ...}`) · `fun json_response(status, body) -> Response` · `fun json_error(status, message) -> Response`
- Wire format: `fun parse_request(text: str) -> Result<Request, HttpError>` · `fun parse_response(text: str, method: str = "GET") -> Result<Response, HttpError>` · `fun format_request(r: Request) -> Result<str, HttpError>` · `fun format_response(r: Response) -> Result<str, HttpError>`
- Gotchas: bodies are `str` of raw bytes (`text()` for UTF-8). Router handlers are sync (no async handlers yet). `serve`/`serve_n` take a *sync* handler, `serve_with` an *async* one. `serve` never returns on its own: run it as `async let` and `task.cancel` it. A time limit on `send_async` comes from `task.timeout`. The module header still says the prelude's `get` took that name, but `http.get` exists (MYLA-393).

```myla
import std.http as http
import std.net as net
from std.http import Request, Response

fun hello(r: Request) -> Response {
    return http.response(200, f"hi {r.path()} {r.query().len()}").with_header("Content-Type", "text/plain")
}

async fun client(url: str) -> str {
    return match await http.fetch_async(url) {
        Ok(resp) => f"{resp.status} {resp.text()} {resp.header("content-type").unwrap_or("?")}"
        Err(e) => f"error: {e}"
    }
}

#main
async fun main() {
    var l = match net.listen(net.addr(net.loopback(), 0)) {
        Ok(l) => l
        Err(e) => {
            print(f"listen: {e}")
            return
        }
    }
    let port = match l.local_addr() {
        Ok(a) => a.port
        Err(e) => 0
    }
    async let server = http.serve_n(l, 1, hello)
    print(await client(f"http://127.0.0.1:{port}/a/b?x=1&y=2"))
    match await server {
        Ok(n) => print(f"served {n}")
        Err(e) => print(f"server: {e}")
    }
    let c = l.close()
}
// output:
// 200 hi /a/b 2 text/plain
// served 1
```

## std.ini
INI (configparser-like, no interpolation). `import std.ini as ini`.
- `enum IniErrorKind { BadSection, NoSeparator, EmptyKey }` · `struct IniError { kind, line: int }` · `struct Ini { entries: [str: [str: str]] }`
- `fun new() -> Ini` · `fun parse(text: str) -> Result<Ini, IniError>` · `fun write(doc: Ini) -> str`
- `.get(section: str, key: str) -> Option<str>` (section "" = before the first header) · `.sections() -> [str]` (without "") · `.keys(section) -> [str]` · `.set(var self, section, key, value)`

## std.io: console output, streams (`Read`, `Write`, `Seek`), buffered I/O
Import: `import std.io as io` or `from std.io import println`. `IoError` is **not** exported from here: `io.IoError` is a module error. Import it from `std.fs` or `std.ioerror`.
- Console:
  - `pub fun println(s: str)`, `pub fun eprint(s: str)`, `pub fun eprintln(s: str)` don't return errors. A closed stdout or stderr pipe ends the program quietly, and other errors are runtime errors.
  - `pub fun write(fd: int32, s: str) -> Result<(), IoError>`, `pub fun errno_text(code: int32) -> str`
  - The builtin `print(x)` needs no import.
- Traits:
  - `pub trait Read { fun read(var self, n: int) -> Result<[uint8], IoError> }` gives `[]` only at the end, and fewer than `n` bytes doesn't mean the end.
  - `pub trait Write { fun write(var self, b: [uint8]) -> Result<int, IoError>; fun flush(var self) -> Result<(), IoError> }`
  - `pub trait Seek { fun seek(var self, pos: SeekFrom) -> Result<int64, IoError> }`
  - `pub trait Pollable { fun descriptor(self) -> int32 }`
  - `pub enum SeekFrom { Start(int64), Current(int64), End(int64) }` is `Eq`.
- Descriptors:
  - `pub struct FdStream { fd: int32 }` implements `Read`, `Write`, `Seek` and `Pollable`. `pub fun fd_stream(fd: int32) -> FdStream`.
  - `async fun write_async(var self, b: [uint8]) -> Result<int, IoError>` must be awaited.
- Memory:
  - `pub struct MemoryStream { data: [uint8], pos: int32 }` implements `Read`, `Write` and `Seek`.
  - `pub fun memory_stream() -> MemoryStream`, `pub fun from_bytes(b: [uint8]) -> MemoryStream`, `pub fun from_str(s: str) -> MemoryStream`
  - `ms.bytes() -> [uint8]`, `ms.text() -> str`, `ms.position() -> int64`. `read_end` and `fill_gap` are internal.
- Buffered reading:
  - `pub struct Buffered<R>`, `pub fun buffered<R: Read>(r: R) -> Buffered<R>`. `pub typealias Reader = Buffered<FdStream>`, with `pub fun stdin() -> Reader` and `pub fun reader(fd: int32) -> Reader`.
  - `impl<R: Read> Buffered<R>`, all `var self`:
    - `b.read_line() -> Result<Option<str>, IoError>`, `b.read_exact(n: int32) -> Result<Option<str>, IoError>`, `b.read_to_end() -> Result<str, IoError>`
    - `b.into_inner() -> R` (takes `self`, not `var self`)
    - Lower level: `b.pull_bytes(n: int32) -> Result<[uint8], IoError>`, `b.pull(n: int32) -> Result<str, IoError>`, `b.fill(want: int32) -> Result<bool, IoError>`. `newline_from` and `take_line` are internal.
  - `Buffered<R>` also implements `Read`, `Seek` when `R: Read + Seek`, and `Pollable` when `R: Pollable`.
  - `impl<R: Read + Pollable> Buffered<R>`: `b.ready(timeout_ms: int32) -> bool`. The **async** variants must be awaited: `b.fill_async(want: int32) -> Result<bool, IoError>`, `b.read_line_async() -> Result<Option<str>, IoError>`, `b.read_exact_async(n: int32) -> Result<Option<str>, IoError>`, `b.read_to_end_async() -> Result<str, IoError>`.
- Buffered writing:
  - `pub struct BufferedWriter<W>`, `pub fun buffered_writer<W: Write>(w: W) -> BufferedWriter<W>` (8 KiB), `pub fun buffered_writer_with<W: Write>(w: W, capacity: int32) -> BufferedWriter<W>`
  - `bw.write_str(s: str) -> Result<int, IoError>`, `bw.drain() -> Result<(), IoError>`, `bw.into_inner() -> Result<W, IoError>`. `push_out` and `make_room` are internal.
  - It implements `Write`, and `Seek` when `W: Write + Seek`.
- Testing: `pub struct ShortReads<R>`, `pub fun short_reads<R: Read>(r: R, most: int32) -> ShortReads<R>`, with `.into_inner() -> R`. It implements `Read`.
- Whole streams: `pub fun read_all<R: Read>(r: R) -> Result<[uint8], IoError>`, `pub fun copy<R: Read, W: Write>(r: R, w: W) -> Result<W, IoError>` (returns `w`, flushed)
- Gotchas:
  - `Read` and `Write` take **bytes only**. Text goes through `Buffered` and `write_str`, or through `s.bytes()` and `bytes.to_str`.
  - `read_line` drops the `\n` but **keeps a `\r`**, unlike `s.lines()`.
  - `read_exact` gives `None` if the input ends first.
  - `BufferedWriter` isn't flushed at exit: call `flush()`.
  - Streams are values: keep one in a `var` (or a field) and use `var self` methods. Functions that take a stream take it by value.
- Prose: `docs/Language/Standard-library/Io.md`

## std.ioerror: `IoError`
Import: `from std.ioerror import IoError` (or the same from `std.fs`).
- `pub enum IoError`:
  - `NotFound`, `PermissionDenied`, `AlreadyExists`, `NotADirectory`, `IsADirectory`, `NotEmpty`, `Interrupted`, `Cancelled`, `Unsupported`, `BrokenPipe`, `InvalidInput`
  - Network: `ConnectionRefused`, `ConnectionReset`, `ConnectionAborted`, `NotConnected`, `AddrInUse`, `AddrNotAvailable`, `TimedOut`, `HostUnreachable`, `NetworkUnreachable`
  - `InvalidData`, `Other(int32)` (a raw errno)
- `e.message() -> str` (`"not found (NotFound)"`), `impl Format` (so `f"{e}"` works)
- `pub fun from_errno(code: int32) -> IoError`, `pub fun io_error_name(e: IoError) -> str`
- Gotcha: **`IoError` is not `Eq`**. `r == Err(IoError.NotFound)` doesn't type-check, so match it instead (`Err(IoError.NotFound) => …`).
- Prose: `docs/Language/Standard-library/Ioerror.md`

## std.iter: lazy adapters over the prelude's `Iterator<T>`
Import: `import std.iter as iter`. Everything is a free function taking the iterator first, chained with `|>`. The sources are `xs.iter()` and `m.iter()` (implicit).
- Sources:
  - `pub fun range(start: int, end: int) -> Range`, where `pub struct Range { at: int, end: int }` implements `Iterator<int>`
  - `pub fun repeat<T>(v: T) -> Repeat<T>` (infinite)
  - `pub fun from_fn<S, T>(state: S, step: (S) -> Option<(T, S)>) -> FromFn<S, T>`
- Adapters, each a `pub struct` with an `impl Iterator`:
  - `map<I: Iterator<T>, T, U>(it: I, f: (T) -> U) -> Map<I, T, U>`
  - `filter(it: I, keep: (T) -> bool) -> Filter<I, T>`
  - `take(it: I, n: int) -> Take<I, T>`, `skip(it: I, n: int) -> Skip<I, T>`
  - `take_while(it: I, pred: (T) -> bool) -> TakeWhile<I, T>`, `skip_while(it: I, pred: (T) -> bool) -> SkipWhile<I, T>`
  - `enumerate(it: I) -> Enumerate<I, T>` (yields `(int, T)`)
  - `zip<A: Iterator<T>, T, B: Iterator<U>, U>(a: A, b: B) -> Zip<A, B, T, U>` (yields `(T, U)`)
  - `chain<A: Iterator<T>, T, B: Iterator<T>>(a: A, b: B) -> Chain<A, B, T>`
  - `flat_map<I: Iterator<T>, T, J: Iterator<U>, U>(it: I, f: (T) -> J) -> FlatMap<I, T, J, U>` (`f` returns an *iterator*, for example `w.chars().iter()`)
- Consumers:
  - `to_list(it: I) -> [T]`, `count(it: I) -> int`, `sum<I, T: Add>(it: I, zero: T) -> T`, `fold<I, T, A>(it: I, init: A, f: (A, T) -> A) -> A`
  - `any(it: I, pred: (T) -> bool) -> bool`, `all(it: I, pred: (T) -> bool) -> bool`, `find(it: I, pred: (T) -> bool) -> Option<T>`
  - `min<I, T: Ord>(it: I) -> Option<T>`, `max<I, T: Ord>(it: I) -> Option<T>`
- Gotchas:
  - There are no methods: `it.map(f)` doesn't exist.
  - `iter.range` is `int` (int32) only.
  - `repeat` needs `take`, or a consumer that stops.
  - Inside your own adapter, loop `while let Some(v) = self.inner.next()`, because a `for` loop works on a copy.
- Prose: `docs/Language/Standard-library/Iter.md`

## std.json
JSON values, parse/print (Python-compatible messages), typed encode/decode with `#derive(Json)`. `import std.json as json`; `from std.json import Json, JsonError` for the types.
- `enum Json { Null, Bool(bool), Int(int64), Float(float64), Str(str), Array([Json]), Object([(str, Json)]) }` (an object keeps order and duplicates)
- `#derive(Eq) enum JsonErrorKind { Syntax, MissingField, WrongType, OutOfRange, UnknownVariant }`
- `#derive(Eq) struct JsonError { kind: JsonErrorKind, msg: str, line: int32, col: int32, path: str }`: `.message() -> str`; `f"{e}"` is `line:col: msg` (syntax) or `$.items[2].n: msg` (typed)
- Parse/print: `fun parse(text: str) -> Result<Json, JsonError>` · `fun to_string(j: Json) -> str` (compact; NaN/inf → `null`) · `fun pretty(j: Json, indent: int = 2) -> str`
- Access: `fun field(j: Json, key: str) -> Option<Json>` (last duplicate) · `fun at(v: Json, path: str) -> Option<Json>` (`"a.b[2].c"`, `""` = itself) · methods `.as_int() -> Option<int64>`, `.as_float() -> Option<float64>` (Int too), `.as_str() -> Option<str>`, `.as_bool() -> Option<bool>`, `.as_list() -> Option<[Json]>`, `.as_object() -> Option<[(str, Json)]>`
- Build: `fun obj(members: [(str, Json)]) -> Json` · `fun arr(items: [Json]) -> Json` · `fun num(x: float64) -> Json` (whole and below 2^53 → `Int`) · `fun text(s: str) -> Json`
- Typed: `trait ToJson { fun to_json(self) -> Json }` · `trait FromJson { fun from_json(j: Json) -> Result<Self, JsonError> }` · `fun encode<T: ToJson>(v: T) -> str` (never fails) · `fun decode<T: FromJson>(text: str) -> Result<T, JsonError>` (`json.decode<P>(s)` or typed by the target)
- Impls exist for all int widths (range-checked; a whole float like `2.0` accepted), `float32/64`, `bool`, `str`, `char` (1-char string), `Json`, `[T]`, `[str: V]`, `Option<T>` (`null`).
- For hand-written `FromJson`: `fun wrong_type(expected: str, found: Json) -> JsonError` · `fun members(j: Json, name: str) -> Result<[(str, Json)], JsonError>` · `fun member<T: FromJson>(fields: [(str, Json)], name: str) -> Result<T, JsonError>` · `fun optional_member<T: FromJson>(fields, name) -> Result<Option<T>, JsonError>`
- `#derive(Json)`: struct → object of fields as named (unknown members ignored; an `Option` field omitted when `None`, absent or `null` reads `None`); enum → `"Red"`, `{"Dot": x}`, `{"Line": [a, b]}`. No renames/attributes. Combine freely: `#derive(Json, Eq)`.
- Gotchas: a tuple field has no JSON form (`derive` error: make it a struct); a map needs `str` keys; `decode` refuses an integer beyond int64 that a float64 doesn't hold exactly (`OutOfRange` at line:col); nesting deeper than 200 is an error.

```myla
import std.json as json
from std.json import Json, JsonError

#derive(Json, Eq)
enum Kind {
    Dot,
    Line(int, int),
}

#derive(Json)
struct Item {
    name: str,
    count: uint8,
    kind: Kind,
    note: Option<str>,
}

fun main() {
    let text = json.encode(Item { name: "a", count: 3, kind: Kind.Line(1, 2), note: None })
    print(text)
    match json.decode<Item>(text) {
        Ok(back) => print(back.kind == Kind.Line(1, 2))
        Err(e) => print(f"{e}")
    }
    let bad: Result<Item, JsonError> = json.decode("{\"name\": \"b\", \"count\": 300, \"kind\": \"Dot\"}")
    if let Err(e) = bad {
        print(f"{e}")
    }
    if let Ok(v) = json.parse("{\"a\": {\"b\": [1, 2.5]}}") {
        print(json.at(v, "a.b[1]").unwrap_or(Json.Null).as_float().unwrap_or(0.0))
    }
}
// output:
// {"name":"a","count":3,"kind":{"Line":[1,2]}}
// true
// $.count: 300 is out of range for uint8
// 2.5
```

## std.log: leveled messages to stderr
Import: `import std.log as log`. The `MYLA_LOG` environment variable sets the level: `error`, `warn` (the default), `info`, `debug` or `off`. The line format is `2026-11-07T17:00:00.123Z INFO msg`.
- `pub enum Level { Error, Warn, Info, Debug }` is `Eq`, with `l.name() -> str`, `l.rank() -> int` and `Format`.
- `pub fun error(message: str)`, `pub fun warn(message: str)`, `pub fun info(message: str)`, `pub fun debug(message: str)`, `pub fun log(level: Level, message: str)`
- `pub fun enabled(level: Level) -> bool`, `pub fun current() -> Option<Level>`, `pub fun threshold(setting: Option<str>) -> Option<Level>`, `pub fun line(at: DateTime, level: Level, message: str) -> str`
- `pub struct Logger { max: Option<Level> }`. Create one with `pub fun logger() -> Logger` (reads `MYLA_LOG` once) or `pub fun logger_at(max: Option<Level>) -> Logger`. Methods: `.enabled(level: Level) -> bool`, `.log(level: Level, msg: str)`, `.error(msg: str)`, `.warn(msg: str)`, `.info(msg: str)`, `.debug(msg: str)`.
- Prose: `docs/Language/Standard-library/Log.md`

## std.math: float64 functions (fdlibm ports, bit-identical on every runner)
Import: `import std.math as math`. These are free functions on `float64`; the same operations are methods of both float types through the implicit `std.float` (`x.sqrt()`).
- `pub const PI`, `TAU`, `E`, `LN2`, `LN10`, `SQRT2: float64`
- Bits and classes: `to_bits(x: float64) -> uint64` (every NaN becomes `0x7FF8…`), `from_bits(bits: uint64) -> float64`, `infinity() -> float64`, `nan() -> float64`, `is_nan(x) -> bool`, `is_infinite(x) -> bool`, `is_finite(x) -> bool`
- Rounding: `copysign(x, s)`, `abs(x)`, `trunc(x)`, `floor(x)`, `ceil(x)`, `round(x)` (halves away from zero), `min(a, b)`, `max(a, b)`. All return `float64`.
- Powers and logarithms: `sqrt(x)`, `hypot(x, y)`, `ldexp(x: float64, k: int32)`, `exp(x)`, `ln(x)`, `log2(x)`, `log10(x)`, `pow(x: float64, y: float64)`
- Trigonometry: `sin(x)`, `cos(x)`, `tan(x)`, `atan(x)`, `atan2(y, x)`, `asin(x)`, `acos(x)`
- Gotchas:
  - `floor` and the other rounding functions return `float64`. Cast with `as int`.
  - Integer powers are `x.pow(e: uint32)` from std.int.
- Prose: `docs/Language/Standard-library/Math.md`

## std.net
TCP/UDP sockets, IP addresses, DNS without libc. `import std.net as net`. Failures are `IoError` (std.ioerror: `ConnectionRefused`, `AddrInUse`, `TimedOut`, `Cancelled`, `Unsupported` on wasm32, …).
- `#derive(Eq, Hash) enum IpAddr { V4(uint8, uint8, uint8, uint8), V6(uint16 ×8) }` · `#derive(Eq, Hash) struct SocketAddr { ip: IpAddr, port: int }` · `enum AddrParseError { Empty, InvalidIp, InvalidPort, MissingPort }` · `enum Shutdown { Read, Write, Both }`
- `fun addr(ip: IpAddr, port: int) -> SocketAddr` (port outside 0..65535: runtime error) · `fun loopback() -> IpAddr` · `loopback_v6()` · `unspecified()` · `unspecified_v6()` · `fun parse_ip(s: str) -> Result<IpAddr, AddrParseError>` · `fun parse_addr(s: str) -> Result<SocketAddr, AddrParseError>` (`"1.2.3.4:80"`, `"[::1]:80"`)
- `IpAddr`: `.is_ipv4()`, `.is_ipv6()`, `.is_loopback()`, `.is_unspecified()`, `.octets() -> [uint8]`; both types `Format` (`f"{a}"`, RFC 5952)
- TCP: `fun listen(a: SocketAddr) -> Result<TcpListener, IoError>` (port 0: system picks; SO_REUSEADDR) · `fun connect(a) -> Result<TcpStream, IoError>` · `fun connect_timeout(a, ms: int)` · `async fun connect_async(a)` · `fun connect_host(host: str, port: int) -> Result<TcpStream, IoError>` (looks the name up)
- `TcpListener`: `.accept() -> Result<TcpStream, IoError>` · `async .accept_async()` · `.local_addr() -> Result<SocketAddr, IoError>` · `.set_timeout(var self, ms: int)` · `.close(var self) -> Result<(), IoError>`
- `TcpStream` (a `Read` and `Write` of std.io: `.read(var self, n) -> Result<[uint8], IoError>` (`[]` = end), `.write(var self, b) -> Result<int, IoError>`, `.flush`): `async .read_async(var self, n: int) -> Result<[uint8], IoError>` · `async .write_async(var self, b: [uint8]) -> Result<int, IoError>` · `.peer_addr()` · `.local_addr()` · `.shutdown(how: Shutdown) -> Result<(), IoError>` · `.set_nodelay(on: bool) -> Result<(), IoError>` · `.set_read_timeout(var self, ms)` · `.set_write_timeout(var self, ms)` · `.close(var self) -> Result<(), IoError>`
- Lines: `fun line_reader(s: TcpStream) -> LineReader`: `async .read_line_async(var self) -> Result<Option<str>, IoError>` · `.read_line(var self)` (blocking) · `.rest(var self) -> [uint8]` (bytes past the last line)
- UDP: `fun udp_bind(a: SocketAddr) -> Result<UdpSocket, IoError>`: `.send_to(b: [uint8], to: SocketAddr) -> Result<int, IoError>` · `.send_str_to(s: str, to)` · `.recv_from(n: int) -> Result<([uint8], SocketAddr), IoError>` · `.recv_str_from(n) -> Result<(str, SocketAddr), IoError>` · `async .recv_from_async(n)` · `async .recv_str_from_async(n)` · `.local_addr()` · `.set_read_timeout(var self, ms)` · `.set_broadcast(on: bool)` · `.close(var self)`
- DNS: `fun lookup(name: str) -> Result<[IpAddr], IoError>` · `struct Resolver { hosts_path: str, servers: [SocketAddr], timeout_ms: int, attempts: int }` · `fun system_resolver() -> Resolver` · `fun resolver(hosts_path: str, servers: [SocketAddr]) -> Resolver` · `.lookup(name)` · `fun hosts_lookup(text: str, name: str) -> [IpAddr]` · `fun nameservers(text: str) -> [SocketAddr]`
- Gotchas: a copy of a stream is the same connection; close sockets yourself. In a task use the `*_async` twins (a blocking `read` or `io.buffered(s).read_line()` holds the worker). A task asked to stop gets `IoError.Cancelled`. The reads/writes are bytes: `bytes.from_str` / `bytes.to_str`.

## std.num: number parsing and formatting
Import: `import std.num as num`.
- `pub enum ParseIntError { Empty, InvalidDigit(int), Overflow }` is `Eq`, with `message()` and `Format`.
- Parsing:
  - `pub fun parse_int(s: str) -> Option<int64>`, `pub fun parse_float(s: str) -> Option<float64>`
  - `pub fun parse_int32(s: str) -> Result<int32, ParseIntError>`, `pub fun parse_int_radix(s: str, radix: int) -> Result<int64, ParseIntError>`
  - `pub fun parse_uint64(s: str) -> Result<uint64, ParseIntError>`, `pub fun parse_uint64_radix(s: str, radix: int) -> Result<uint64, ParseIntError>`
- Formatting:
  - `pub fun format_float(x: float64) -> str` (Python repr), `pub fun format_fixed(x: float64, prec: int32) -> str`
  - `pub fun to_radix(n: int64, radix: int) -> str`, `pub fun to_radix_u64(n: uint64, radix: int) -> str`
  - `pub fun to_hex(n: uint64, width: int = 0) -> str`, `pub fun to_binary(n: uint64, width: int = 0) -> str`
- Internal (literals): `f64_literal_bits(lexeme: str) -> uint64`, `f32_round_bits(bits: uint64) -> uint64`, `float_from_bits(bits: uint64) -> float64`, `pow2(k: int32) -> float64`
- Gotchas:
  - **`parse_int` is `Option<int64>`, not `int`**: `let v: int = num.parse_int(s).unwrap_or(0)` is a type error. Use `parse_int32` (a `Result`) for an `int`.
  - `parse_int` and `parse_float` are `Option`s, but the others are `Result`s.
  - `format_float` writes Python's repr (`1.0`, `1e+16`), **not** what `print` and f-strings write (`1`, `1e16`).
  - A radix outside 2..36 is a runtime error.
- Prose: `docs/Language/Standard-library/Num.md`

## std.path: lexical path operations (no filesystem access)
Import: `import std.path as path`.
- `pub fun is_absolute(p: str) -> bool`, `pub fun join(a: str, b: str) -> str` (an absolute `b` replaces `a`), `pub fun join_all(parts: [str]) -> str`
- `pub fun parent(p: str) -> Option<str>`, `pub fun file_name(p: str) -> Option<str>`, `pub fun stem(p: str) -> Option<str>`, `pub fun extension(p: str) -> Option<str>` (without the dot)
- `pub fun with_extension(p: str, ext: str) -> str`, `pub fun components(p: str) -> [str]`, `pub fun normalize(p: str) -> str`, `pub fun relative(from_dir: str, to: str) -> Option<str>`
- Prose: `docs/Language/Standard-library/Path.md`

## std.platform, std.platform_aarch64, std.platform_wasm, std.rt
Runtime internals, not for programs. `std.rt` is the runtime written in Myla that a native build loads with every program (string concat/compare, maps, printing, files, processes, sockets `sock_*`, the heap, the executor/timers/notifiers, `exit_program`); it uses the `__load64`/`__store64`/`__syscall`… primitives that only the standard library may call (D152). `std.platform` is its OS layer: Linux x86-64; `platform_aarch64.my` and `platform_wasm.my` stand in for it on `--target aarch64-linux` and `wasm32-wasi` (WASI preview 1: no processes, no sockets, one worker). The only thing a program can usefully take: `from std.platform import TARGET` (`pub const TARGET: str`, `"x86_64-linux"`, `"aarch64-linux"` or `"wasm32-wasi"`: the target being built for). Documented in `docs/Language/Standard-library/Rt.md`.

## std.process: arguments, environment, exit, child processes
Import: `import std.process as process`.
- `pub fun args() -> [str]` (`[0]` is the program), `pub fun exit(code: int32)`, `pub fun env(name: str) -> Option<str>`
- `pub enum ExitStatus { Exited(int32), Signaled(int32) }` is `Eq`.
- `pub struct Output { stdout: [uint8], stderr: [uint8], status: ExitStatus }`
- `pub enum SpawnError { NotFound, PermissionDenied, Unsupported, Cancelled, InvalidInput, WorkingDir(int32), Other(int32) }` is `Eq`, with `message()` and `Format`.
- `pub enum Stdio { Piped, Inherit, Null }` is `Eq`.
- One-shot: `pub fun run(program: str, args: [str]) -> Result<Output, SpawnError>`, `pub async fun run_async(program: str, args: [str]) -> Result<Output, SpawnError>` (must be awaited)
- Builder: `pub struct Command` (opaque fields), `pub fun command(program: str) -> Command`. Each `Command` method returns a new `Command`:
  - Arguments and environment: `.arg(a: str)`, `.args(extra: [str])`, `.cwd(dir: str)`, `.env(name: str, value: str)`, `.env_remove(name: str)`, `.env_clear()`
  - Input: `.stdin(text: str)`, `.stdin_from(how: Stdio)`, `.stdin_from_stdout(out: ChildStdout)`
  - Output: `.stdout_from(how: Stdio)`, `.stderr_from(how: Stdio)`
- Running a command:
  - `.output() -> Result<Output, SpawnError>`, `async .output_async() -> Result<Output, SpawnError>`
  - `.spawn() -> Result<Child, SpawnError>`, `.spawn_for_output() -> Result<Child, SpawnError>`
  - `.pipe(next: Command) -> Pipeline`
  - Internal: `stdio_letters`, `spawn_opts`, `opts`, `opts_with`
- `pub struct Pipeline { first: Command, second: Command }`, with `.output() -> Result<PipelineOutput, SpawnError>`. `pub struct PipelineOutput { first: Output, second: Output }`.
- Child stream types:
  - `pub struct ChildStdin { fd: int32 }` implements `io.Write` and `Pollable`. It has `async write_async(var self, b: [uint8]) -> Result<int, IoError>` and `close(var self) -> Result<(), IoError>`.
  - `pub struct ChildStdout { fd: int32 }` and `pub struct ChildStderr { fd: int32 }` implement `io.Read` and `Pollable`. Each has `close(var self) -> Result<(), IoError>`.
- `pub struct Child`:
  - `c.id() -> int32`
  - Taking streams (`var self`): `c.take_stdin() -> Option<ChildStdin>`, `c.take_stdout() -> Option<ChildStdout>`, `c.take_stderr() -> Option<ChildStderr>`
  - Waiting (`var self`): `c.try_wait() -> Result<Option<ExitStatus>, IoError>`, `c.wait() -> Result<ExitStatus, IoError>`, `c.wait_with_output() -> Result<Output, IoError>`, `c.kill() -> Result<(), IoError>`
  - The async variants must be awaited: `c.wait_async()`, `c.wait_with_output_async()`
  - Internal: `forget_exited`, `close_input`, `drain`, `reap`, `drain_async`, `reap_async`
- Gotchas:
  - **`Output.stdout` and `Output.stderr` are `[uint8]`**: use `bytes.to_str(out.stdout)`.
  - A program that can't start gives a `SpawnError`, but a nonzero exit is `Ok` with `status == ExitStatus.Exited(n)`.
  - The program is looked up in `PATH` unless it contains a `/`.
  - Everything is `Unsupported` on wasm32.
  - A `Command` is an immutable value (D147).
- Prose: `docs/Language/Standard-library/Process.md`

## std.random: xoshiro256** generator (not for secrets)
Import: `import std.random as random`.
- `pub struct Rng { s0: uint64, s1: uint64, s2: uint64, s3: uint64 }` is `Eq`. Create one with `pub fun seeded(seed: uint64) -> Rng` or `pub fun from_os() -> Rng`.
- `impl Rng`, all `var self`:
  - Bits: `r.next_u64() -> uint64`, `r.next_u32() -> uint32`, `r.below(n: uint64) -> uint64`
  - Ranges: `r.int_in(lo: int, hi: int) -> int`, `r.int64_in(lo: int64, hi: int64) -> int64`
  - Other values: `r.float() -> float` (in [0, 1)), `r.boolean() -> bool`
  - Lists: `r.shuffled<T>(xs: [T]) -> [T]`, `r.choice<T>(xs: [T]) -> Option<T>`
- Gotchas:
  - `int_in` excludes `hi`, and an empty range is a runtime error.
  - The generator must be a `var`, and a copy repeats the same numbers.
  - A `seed` held in an `int` variable needs `as uint64`.
- Prose: `docs/Language/Standard-library/Random.md`

## std.regex
RE2/Go syntax, linear time (Pike VM + lazy DFA), byte-oriented. `import std.regex as regex`.
- `#derive(Eq) enum ErrorKind { MissingParen, UnexpectedParen, MissingBracket, InvalidEscape, InvalidClassRange, InvalidPosixClass, NonAsciiInClass, MissingRepeatArgument, InvalidNestedRepeat, InvalidRepeatCount, InvalidGroup, InvalidGroupName, DuplicateGroupName, InvalidFlags, NestingTooDeep, TooLarge }`
- `#derive(Eq) struct RegexError { kind: ErrorKind, pos: int }` (`f"{e}"` = `missing closing ) at 0`)
- `struct Regex` (opaque) · `#derive(Eq) struct Match { start: int, end: int, text: str }` (byte offsets) · `struct Captures`
- `fun compile(pattern: str) -> Result<Regex, RegexError>` · `fun escape(s: str) -> str`
- `Regex`: `.as_str() -> str` · `.group_count() -> int` (without group 0) · `.is_match(s) -> bool` · `.find(s) -> Option<Match>` · `.find_at(s, start: int) -> Option<Match>` · `.find_all(s) -> [Match]` · `.captures(s) -> Option<Captures>` · `.captures_all(s) -> [Captures]` · `.replace(s, with: str) -> str` · `.replace_all(s, with) -> str` · `.replacen(s, with, limit: int) -> str` · `.split(s) -> [str]` (`n` matches → `n + 1` pieces)
- `Captures`: `.len() -> int` (with group 0) · `.get(i: int) -> Option<Match>` · `.name(n: str) -> Option<Match>` · `.text(i: int) -> str` ("" if it didn't take part)
- Replacement syntax: `$1`, `${1}`, `$name`, `${name}`, `$$`. Named groups `(?P<name>…)` or `(?<name>…)`; flags `(?i)`, `(?m)`, `(?s)`, `(?U)`.
- Gotchas: no backreferences, no lookaround (`(?=` is `InvalidGroup`). Classes and `.` match one *byte*; a non-ASCII char in a class (`[é]`) is an error, but a non-ASCII literal outside a class is one atom (`é+` repeats the whole char). Case folding is ASCII. Escape `\` in Myla strings: `"\\d+"`.

```myla
import std.regex as regex

fun main() {
    match regex.compile("(?P<key>[a-z]+)=(\\d+)") {
        Ok(re) => {
            if let Some(m) = re.find("x a=12 b=3") {
                print(f"{m.start} {m.end} {m.text}")
            }
            if let Some(c) = re.captures("b=7") {
                print(c.text(2))
                if let Some(k) = c.name("key") {
                    print(k.text)
                }
            }
            print(re.replace_all("a=1,b=2", "$2:${key}"))
        }
        Err(e) => print(f"{e}")
    }
}
// output:
// 2 6 a=12
// 7
// b
// 1:a,2:b
```

## std.set
Hash set in insertion order (a map to `()`). `import std.set as set`.
- `struct Set<T>` (`T: Eq + Hash`) · `fun new<T: Eq + Hash>() -> Set<T>` · `fun of<T: Eq + Hash>(xs: [T]) -> Set<T>`
- `.insert(var self, x: T) -> bool` (true if new) · `.remove(var self, x) -> bool` · `.contains(x) -> bool` · `.len() -> int` · `.is_empty() -> bool` · `.items() -> [T]` · `.iter() -> list.ListIter<T>` · `.union(o: Set<T>) -> Set<T>` · `.intersection(o)` · `.difference(o)` · `.is_subset(o) -> bool`
- `==` (same elements, any order). Gotcha: `let s = set.new()` can't infer `T`: `var s: set.Set<str> = set.new()` or `set.new<str>()`. No `symmetric_difference` (bitset has it).

## std.signal: catch Ctrl-C and SIGTERM
Import: `import std.signal as signal`.
- `pub enum Signal { Interrupt, Terminate }` is `Eq + Hash`, with `Format`. `pub enum SignalError { Unsupported, Cancelled, Other(int) }` is `Eq`, with `message()` and `Format`.
- `pub fun listen() -> Result<Signals, SignalError>`, where `pub struct Signals { handle: int }` has:
  - **async** `s.next() -> Result<Signal, SignalError>`
  - `s.try_next() -> Option<Signal>`, `s.close()`
- `pub async fun interrupted() -> Result<Signal, SignalError>` (must be awaited)
- Prose: `docs/Language/Standard-library/Signal.md`

## std.slice: slice indexing (compiler and runtime internal)
- `pub struct Range { first: int64, step: int64, count: int64 }`
- `pub fun range_of(n: int64, start: int64, has_start: bool, start_end: bool, stop: int64, has_stop: bool, stop_end: bool, step: int64) -> Range`
- The same eight trailing parameters (`start`, `has_start`, `start_end`, `stop`, `has_stop`, `stop_end`, `step`) are taken by `take<T>(xs: [T], …) -> [T]`, `str_whole(s: str, …) -> bool` and `take_str(s: str, …) -> str`.
- It implements `xs[a:b:step]` and `^n`. Programs use the syntax, not these functions.
- Prose: `docs/Language/Standard-library/Slice.md`

## std.task
Run-time task sets, timers, notifiers, channels, pools (D89, D96, D124, MYLA-351, MYLA-387). `import std.task as task`. Async lambdas: `async () => await f(x)`, type `async () -> T`, `async (J) -> R`.
- `async fun all<T>(fs: [async () -> T]) -> [T]` (children at once; results in order of `fs`)
- `fun cancel<T>(child: T)` (argument: the name of an `async let`; compiler-handled; cooperative) · `fun cancelled() -> bool`
- `async fun yield()` · `async fun sleep(ms: int)` · `async fun timeout<T>(ms: int, f: async () -> T) -> Option<T>` (`None` if time ran out; the child is cancelled and awaited either way)
- Notifiers: `#derive(Eq, Hash) struct Notifier`, `struct Listener` · `fun notifier() -> Notifier`
  - `Notifier`: `.notify_one()` (wakes longest waiter or leaves a permit) · `.notify_all()` (no permit) · `.close()` (waiters get `false`; any later use is the runtime error "use of a closed notifier") · `async .wait() -> bool` · `async .wait_timeout(ms: int) -> bool` · `.listen() -> Listener`
  - `Listener`: `async .wait() -> bool` · `async .wait_timeout(ms: int) -> bool` (end at once if a `notify_all` came after `listen`)
- Channels: `#derive(Eq) enum ChannelError { Closed, Full, Empty, TimedOut, Cancelled }` (`.message()`, `Format`) · `struct Channel<T>` (a handle: copies share the queue)
  - `fun channel<T>(cap: int) -> Channel<T>` (`cap <= 0`: rendezvous) · `fun unbounded<T>() -> Channel<T>`
  - every method is `async`: `.send(x: T) -> Result<(), ChannelError>` (`Closed`, `Cancelled`) · `.send_timeout(x, ms: int) -> Result<(), ChannelError>` (`TimedOut`) · `.try_send(x) -> Result<(), ChannelError>` (`Full`, `Closed`) · `.recv() -> Option<T>` (`None`: closed and drained, or cancelled) · `.recv_timeout(ms: int) -> Result<T, ChannelError>` · `.try_recv() -> Result<T, ChannelError>` (`Empty`, `Closed`) · `.close()` (idempotent) · `.len() -> int`
- Pools: `async fun pool<J, R>(n: int, jobs: [J], f: async (J) -> R) -> [R]` (results in job order) · `async fun workers<J, R>(n: int, jobs: Channel<J>, results: Channel<R>, f: async (J) -> R) -> int` (results as they finish; closes `results`; returns the count sent) · `async fun first<T>(fs: [async () -> T]) -> Option<(int, T)>` (index and result of the first to finish; the rest cancelled and awaited)
- Gotchas: even `close()`, `len()`, `try_send`, `try_recv` must be awaited (`a call to the async method 'send' needs 'await'`). Type a channel from outside: `let ch: task.Channel<int> = task.channel(4)` or `task.channel<int>(4)`. A send result you don't use still needs binding (`let r = await ch.send(x)`); an `async let` of a unit function is awaited with `await p`.

```myla
import std.task as task

async fun produce(ch: task.Channel<int>, n: int) {
    for i in 0..n {
        let r = await ch.send(i * i)
    }
    await ch.close()
}

async fun slow(ms: int) -> int {
    await task.sleep(ms)
    return ms
}

#main
async fun main() {
    let ch: task.Channel<int> = task.channel(2)
    async let p = produce(ch, 5)
    var total = 0
    while let Some(x) = await ch.recv() {
        total += x
    }
    await p
    print(total)
    match await ch.send(1) {
        Ok(()) => print("sent")
        Err(e) => print(f"{e}")
    }
    let tens = await task.pool(2, [1, 2, 3], async (x: int) => x * 10)
    print(tens[2])
    print(await task.timeout(5, async () => await slow(1000)) == None)
    if let Some((i, v)) = await task.first([async () => await slow(30), async () => await slow(1)]) {
        print(f"first {i} {v}")
    }
}
// output:
// 30
// channel closed
// 30
// true
// first 1 1
```

## std.term: terminal detection, styles, cursor, keys, line editor
Import: `import std.term as term`.
- `pub enum Stream { Stdin, Stdout, Stderr }` is `Eq + Hash`. `pub enum TermError { NotATerminal, Unsupported, Interrupted, Other(int) }` is `Eq`, with `message()` and `Format`.
- Detection: `pub fun is_tty(s: Stream) -> bool`, `pub fun size() -> Option<(int, int)>` (columns, rows), `pub fun size_of(s: Stream) -> Option<(int, int)>`, `pub fun enable_ansi(s: Stream) -> bool`, `pub fun colors(s: Stream) -> bool` (honors `NO_COLOR` and `TERM=dumb`)
- Raw mode: `pub fun raw_mode() -> Result<RawMode, TermError>`, then `raw.restore() -> Result<(), TermError>`
- Colors: `pub enum Color { Default, Black, Red, Green, Yellow, Blue, Magenta, Cyan, White, BrightBlack, BrightRed, BrightGreen, BrightYellow, BrightBlue, BrightMagenta, BrightCyan, BrightWhite, Index(int), Rgb(int, int, int) }`
- Styles:
  - `pub struct Style` is `Eq`. Create one with `pub fun style() -> Style`.
  - Each method returns a new `Style`: `.fg(c: Color)`, `.bg(c: Color)`, `.bold()`, `.dim()`, `.italic()`, `.underline()`, `.reverse()`, `.strike()`, `.with(a: int)`
  - Also `.is_plain() -> bool`, `.sgr() -> str`, `.paint(text: str) -> str`
  - `pub fun colored(text: str, c: Color) -> str`, `pub fun reset() -> str`
- Escape sequences, each a function returning `str`: `cursor_up(n: int)`, `cursor_down(n: int)`, `cursor_right(n: int)`, `cursor_left(n: int)`, `cursor_column(col: int)`, `move_to(row: int, col: int)`, `clear_screen()`, `clear_line()`, `clear_to_end()`, `hide_cursor()`, `show_cursor()`
- Text: `pub fun strip(s: str) -> str` (removes escape sequences), `pub fun width(s: str) -> int` (terminal columns), `pub fun char_width(c: char) -> int`
- Keys:
  - `pub enum Key { Char(char), Ctrl(char), Alt(char), Enter, Tab, Backspace, Escape, Up, Down, Left, Right, Home, End, PageUp, PageDown, Insert, Delete, F(int), Unknown(str) }`
  - `pub fun parse_key(s: str) -> Option<(Key, int)>`
  - `pub fun key_reader() -> KeyReader`, with `kr.next() -> Result<Option<Key>, TermError>` (`var self`)
- Line editing:
  - `pub struct LineEdit { chars: [char], cursor: int, hist: int, draft: [char] }`, `pub fun line_edit(history: int) -> LineEdit`
  - `LineEdit` methods: `.text() -> str`, `.apply(k: Key, history: [str]) -> EditStep`, `.render(prompt: str, cols: int) -> str`. `control`, `insert`, `delete_back`, `delete_here`, `move_to` and `go_history` are helpers.
  - `pub enum EditStep { Editing, Accept, EndOfInput, Cancel }`
- Editor (what `myla repl` uses): `pub struct Editor`, `pub fun editor(out: Stream) -> Editor`, with `.add_history(line: str)`, `.read_line(prompt: str) -> Result<Option<str>, TermError>` and `.columns() -> int`
- Gotchas:
  - The escape functions *return* strings: print them yourself.
  - Restore raw mode with `defer { let r = raw.restore() }`.
  - On wasm32, nothing is a terminal.
- Prose: `docs/Language/Standard-library/Term.md`

## std.test: helpers for `#test` functions and the native harness
Import: `import std.test as t`.
- Checks:
  - `pub fun expect(cond: bool, msg: str = "expectation failed")`
  - `pub fun expect_eq<T: Eq + Format>(got: T, want: T)` fails with `expected W, got G`
  - `pub fun expect_ne<T: Eq + Format>(got: T, other: T)`, `pub fun fail(msg: str)`
  - Every failure is a `panic`.
- Scratch files: `pub fun temp_dir() -> str`, `pub fun temp_file() -> str`. Both are removed when the case ends, and both are runtime errors outside `myla test`.
- Projects: `pub fun program() -> str` gives the built project program, for the tests in `tests/`.
- Harness internals, used by `myla test --native`:
  - `pub struct Case { name: str, kind: int32, message: str, code: int32 }`
  - Run control: `case_index(argv: [str]) -> int32`, `from_index(argv: [str]) -> int32`, `case_begin()`, `case_end(detail: str)`, `cut_run(stdout: str, stderr: str, code: int32) -> [(str, str, int32)]`, `child_done(detail: str)`, `run_in_children(program: str, cases: [Case]) -> Option<int32>`
  - Reporting: `case_lines(c: Case, detail: str, shown: [str]) -> [str]`, `case_detail(c: Case, stdout: str, stderr: str, code: int32) -> (str, [str])`, `case_outcome(c: Case, stdout: str, stderr: str, code: int32) -> (str, [str], str)`, `report_inline(c: Case, detail: str) -> bool`, `end(status: int32)`, `summary(passed: int32, total: int32) -> int32`
  - Formatting: `repr_str(s: str) -> str`, `repr_float(v: float64) -> str`, `without_module_ids(text: str) -> str`
- Gotchas:
  - **`expect_eq` needs `Format`**, which integers, floats, `str`, `char`, `bool` and types with `impl Format` have. Lists, tuples, `Option`, `Result` and `#derive(Eq)` structs don't: use `t.expect(xs == [1, 2], "…")`.
  - There's no `assert_eq`. The builtin `assert(cond, msg)` exists.
- Prose: `docs/Language/Standard-library/Test.md`

```myla
import std.test as t
import std.fs as fs

#test
fun writes_a_file() {
    let d = t.temp_dir()                            // removed when the case ends
    let p = d + "/x.txt"
    t.expect(fs.write_to_file(p, "hi").is_ok(), "write")
    t.expect_eq(fs.read_to_string(p).unwrap_or(""), "hi")   // T: Eq + Format
    t.expect([1, 2].reversed() == [2, 1], "lists aren't Format: use expect")
}
```

## std.text: scanner for parsing, number extraction, wrapping, columns
Import: `import std.text as text`.
- Errors:
  - `pub enum ScanErrorKind { Expected(str), NoInt, Overflow, NoIdent, Other(str) }` is `Eq`.
  - `pub struct ScanError { kind: ScanErrorKind, pos: int, line: int, col: int }` is `Eq`, with `message()` and `Format` (`"2:7: expected an integer"`).
- Scanner:
  - `pub struct Scanner { text: str, pos: int }`, `pub fun scanner(text: str) -> Scanner`
  - Looking: `sc.at_end() -> bool`, `sc.rest() -> str`, `sc.peek() -> Option<char>`
  - Reading (`var self`): `sc.next() -> Option<char>`, `sc.take_while(pred: (char) -> bool) -> str`, `sc.skip_space()`, `sc.eat(lit: str) -> bool`, `sc.expect(lit: str) -> Result<(), ScanError>`, `sc.int() -> Result<int, ScanError>`, `sc.long() -> Result<int64, ScanError>`, `sc.ident() -> Result<str, ScanError>`
  - `sc.error(kind: ScanErrorKind) -> ScanError` builds an error at the current position.
- Numbers: `pub fun ints(line: str) -> Result<[int], ScanError>`, `pub fun longs(line: str) -> Result<[int64], ScanError>`
- Layout:
  - `pub fun wrap(text: str, width: int) -> [str]`, `pub fun fill(text: str, width: int) -> str`
  - `pub enum Align { Left, Right }` is `Eq`. `pub fun columns(rows: [[str]], align: [Align], sep: str = "") -> str`
  - `pub fun indent(text: str, prefix: str) -> str`, `pub fun dedent(text: str) -> str`
- Gotchas:
  - `ints` returns a **`Result`**, so `?` it or match it.
  - In `ints`, `"5-3"` gives `[5, 3]`: a `-` after a letter or a digit isn't a sign.
  - `Scanner.next` is a `var self` method, not `Iterator`.
- Prose: `docs/Language/Standard-library/Text.md`

## std.time: monotonic clock, `Duration`, `Instant`, UTC `DateTime`
Import: `import std.time as time`. There is no sleep here: use `await task.sleep(ms)` from std.task. There are no time zones.
- Clock: `pub fun now_ns() -> int64`, `pub fun now_ms() -> int64` (monotonic)
- `pub struct Duration { ns: int64 }`:
  - It is `Eq`, `Add`, `Sub` and `Ord`, and its `Format` is Go's (`1.5s`, `2h3m4s`).
  - Making one: `nanos(n: int64)`, `micros(n: int64)`, `millis(n: int64)`, `seconds(n: int64)`, `minutes(n: int64)`, `hours(n: int64)`. Each returns a `Duration`.
  - Reading it: `.as_nanos() -> int64`, `.as_micros() -> int64`, `.as_millis() -> int64`, `.as_secs() -> int64`, `.as_secs_f64() -> float64`
  - Arithmetic: `.abs() -> Duration`, `.mul_int(k: int64) -> Duration`, `.div_int(k: int64) -> Duration`
- `pub struct Instant { ns: int64 }` is `Eq` and `Ord`. `pub fun now() -> Instant`, with `.elapsed() -> Duration`, `.since(earlier: Instant) -> Duration` and `.add(d: Duration) -> Instant`.
- `pub enum TimeError { Syntax(int), Field(str), OutOfRange }` is `Eq`, with `message()` and `Format`.
- Calendar: `pub fun is_leap_year(year: int) -> bool`, `pub fun days_in_month(year: int, month: int) -> int`. `pub enum Weekday { Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday }` is `Eq`, with `.number() -> int` (Monday is 1), `.name() -> str` and `Format`.
- `pub struct DateTime { year: int, month: int, day: int, hour: int, minute: int, second: int, nanosecond: int }`:
  - It is `Eq` and `Ord`, and its `Format` is RFC 3339.
  - Making one:
    - `datetime(year: int, month: int, day: int, hour: int, minute: int, second: int, nanosecond: int) -> Result<DateTime, TimeError>`
    - `date(year: int, month: int, day: int) -> Result<DateTime, TimeError>`
    - `from_unix(secs: int64, nanos: int64) -> Result<DateTime, TimeError>`, `from_unix_ns(ns: int64) -> DateTime`
    - `now_utc() -> DateTime`
  - Methods: `.to_unix() -> int64`, `.to_unix_ns() -> Result<int64, TimeError>`, `.weekday() -> Weekday`, `.day_of_year() -> int`, `.add(d: Duration) -> Result<DateTime, TimeError>`, `.diff(other: DateTime) -> Duration`
- Formatting, each returning `str`: `format_rfc3339(t: DateTime)`, `format_rfc3339_millis(t: DateTime)`, `format_iso8601_basic(t: DateTime)`, `format_date(t: DateTime)`
- Parsing: `parse_rfc3339(s: str) -> Result<DateTime, TimeError>`, `parse_iso8601(s: str) -> Result<DateTime, TimeError>`
- Gotchas:
  - The `Duration` constructors take `int64`, so a literal works but an `int` variable needs `as int64`.
  - `DateTime.add` returns a `Result`, but `Instant.add` doesn't.
  - Measure time with `Instant`, not `now_utc` (the wall clock can go back).
  - `MYLA_TIME=virtual` makes the interpreter's clock move only when every task sleeps.
- Prose: `docs/Language/Standard-library/Time.md`

## std.toml
TOML 1.0 read/write, positions, typed encode/decode with `#derive(Toml)`. `import std.toml as toml`.
- `enum Toml { Str(str), Int(int64), Float(float64), Bool(bool), DateTime(TomlDateTime), Date(TomlDate), Time(TomlTime), Array([Toml]), Table([(str, Toml)]) }` (`Eq`, NaN == NaN)
- `#derive(Eq) struct TomlDate { year: int32, month: int32, day: int32 }` · `struct TomlTime { hour, minute, second, nanosecond: int32 }` · `struct TomlDateTime { date: TomlDate, time: TomlTime, offset: Option<int32> }` (minutes; `None` = local)
- `#derive(Eq) enum TomlErrorKind { Syntax, MissingField, WrongType, OutOfRange, UnknownVariant }` · `#derive(Eq) struct TomlError { kind, msg: str, line: int32, col: int32, path: str }` (`.message()`, `Format` as JsonError)
- `#derive(Eq) struct TomlPos { line, col, end_line, end_col: int32 }` · `struct TomlDoc { root: Toml, … }`
- `fun parse(text: str) -> Result<Toml, TomlError>` · `fun parse_doc(text: str) -> Result<TomlDoc, TomlError>` · `fun key_pos(d: TomlDoc, path: [str]) -> Option<TomlPos>` · `fun value_pos(d: TomlDoc, path: [str]) -> Option<TomlPos>` · `fun field(t: Toml, key: str) -> Option<Toml>`
- `fun to_string(doc: Toml) -> str` (round-trips through `parse`) · `fun inline_string(v: Toml) -> str` (one value as on the right of `=`)
- Typed: `trait ToToml { fun to_toml(self) -> Toml }` · `trait FromToml { fun from_toml(t: Toml) -> Result<Self, TomlError> }` · `fun encode<T: ToToml>(v: T) -> Result<str, TomlError>` (`WrongType` unless it is a table) · `fun decode<T: FromToml>(text: str) -> Result<T, TomlError>` · helpers `wrong_type`, `members`, `member<T>`, `optional_member<T>` as in std.json.
- Impls: all ints, `float32/64`, `bool`, `str`, `char`, `TomlDateTime`, `TomlDate`, `TomlTime`, `Toml`, `[T]`, `[str: V]`; no `Option<T>` impl (only as a derived struct's field, omitted when `None`).
- Gotchas: no `as_*`/`at` helpers (match `Toml.Table(ms)` or use `field`); `encode` is a `Result`, `json.encode` isn't. Enums as with JSON: `"Red"`, `{ Dot = x }`, `{ Line = [a, b] }`.

## std.unionfind
Disjoint sets over 0..n-1 (path compression + union by rank). `import std.unionfind as unionfind`.
- `struct UnionFind` · `fun new(n: int) -> UnionFind`
- `.len() -> int` · `.sets() -> int` · `.add(var self) -> int` (new element) · `.find(var self, x: int) -> int` · `.union(var self, a, b) -> bool` (false if already joined) · `.same(var self, a, b) -> bool` · `.size_of(var self, x) -> int` · `.groups(var self) -> [[int]]`
- Gotcha: `find`, `same`, `size_of`, `groups` take `var self` (path compression): the union-find must be a `var`.

## std.url: RFC 3986 URLs, percent and query encoding
Import: `import std.url as url`.
- `pub enum UrlError { BadPercent(int), BadChar(int), BadScheme(int), BadHost(int), BadPort(int) }` is `Eq`, with `message()` and `Format`.
- `pub struct Url { scheme: str, user_info: Option<str>, host: Option<str>, port: Option<int>, path: str, query: Option<str>, fragment: Option<str> }` is `Eq + Hash`, with `.to_str() -> str` and `.resolve(r: Url) -> Url`.
- `pub fun parse(s: str) -> Result<Url, UrlError>` (no decoding), `pub fun resolve(base: str, reference: str) -> Result<str, UrlError>`
- `pub fun percent_encode(s: str, safe: str = "") -> str`, `pub fun percent_decode(s: str) -> Result<str, UrlError>` (`+` stays as it is)
- `pub fun query_encode(pairs: [(str, str)]) -> str`, `pub fun query_decode(s: str) -> Result<[(str, str)], UrlError>` (`+` becomes a space)
- Prose: `docs/Language/Standard-library/Url.md`

## std.uuid: UUID v4 and v7
Import: `import std.uuid as uuid`.
- `pub struct Uuid { hi: uint64, lo: uint64 }` is `Eq + Hash`, `Ord` and `Format`. Methods: `.to_str() -> str`, `.bytes() -> [uint8]`, `.version() -> int`, `.unix_ms() -> Option<int64>`.
- `pub enum UuidError { Length(int), Syntax(int), ByteLength(int) }` is `Eq`, with `message()` and `Format`.
- `pub fun nil() -> Uuid`, `pub fun max() -> Uuid`, `pub fun v4() -> Uuid`, `pub fun v7() -> Uuid` (from OS entropy)
- `pub fun parse(s: str) -> Result<Uuid, UuidError>` (8-4-4-4-12 only), `pub fun from_bytes(b: [uint8]) -> Result<Uuid, UuidError>`
- `pub struct Generator { rng: random.Rng }`, `pub fun generator(rng: random.Rng) -> Generator`, with `.v4() -> Uuid` and `.v7(unix_ms: int64) -> Uuid` (`var self`)
- Prose: `docs/Language/Standard-library/Uuid.md`

## std.vector, std.matrix, std.quaternion (and std.vector32, std.matrix32, std.quaternion32)
Purpose: linear algebra for graphics and numerics (D201, MYLA-587). The plain modules are `float64`, the `32` ones `float32` with the same names (`vector32.Vec3`), all six GENERATED by `scripts/gen_std_linalg.py` (edit the script; `--check` in `test_linalg`). `x.to_f32()` / `x.to_f64()` convert between twins.
- std.vector: `Vec2`/`Vec3`/`Vec4` `{ x, y[, z[, w]] }` (`#derive(Eq, Hash)`, print `(1, 2, 3)`), `vec3(x, y, z)`, `splat3(s)`, `Vec3.zero()`, `Vec3.one()`. Operators: `+ - * /` by component, `v * s`, `s * v`, `v / s`, `-v`, `v[i]`, `v[i] = s`. Methods: `dot`, `length`, `length_squared`, `normalized` (NaN for zero), `try_normalized -> Option`, `distance`, `distance_squared`, `lerp(o, t)`, `min`, `max`, `abs`, `min_element`, `max_element`, `reflect(n)`, `project_onto(o)`, `angle_between(o)`, `to_list`; `Vec2.perp()`, `perp_dot`, `extend(z)`; `Vec3.cross(o)`, `extend(w)`, `truncate()`; `Vec4.truncate()`. `Vector { data: [S] }` of any length: `vector(xs)`, `zeros(n)`, `filled(n, v)`, the same operators (lengths checked: `vector lengths differ: 2 and 3`), `len`, `dot`, `length`, `normalized`, `distance`, `sum`, `map(f)`, `to_list`.
- std.matrix: column-major `Mat2`/`Mat3`/`Mat4`, fields = columns `x_axis`, `y_axis`, `z_axis`, `w_axis`; `m * v` (column vectors: `a * b * v` applies `b` first). `mat3(c0, c1, c2)` (columns), `mat3_from_rows(r0, r1, r2)`, `Mat3.identity()`, `Mat3.zero()`. Operators: `a * b`, `m * v`, `m * s`, `s * m`, `+`, `-`, `-m`, `m[(row, col)]` (and `= s`), `m[i]` a column (and `= col`). Methods: `col(i)`, `row(i)`, `transpose`, `determinant`, `inverse -> Option`, `trace`, `to_list` (column-major), `to_matrix`; `Mat3.to_mat4()`, `transform_point2`, `transform_vector2`; `Mat4.upper_left()`, `transform_point3` (affine, no divide), `transform_vector3`, `project_point3` (divides by w). Free functions: `rotation2(a) -> Mat2`, `translation2d(v)`, `rotation2d(a)`, `scaling2d(v)` (affine Mat3); `translation(v)`, `scaling(v)`, `rotation_x/y/z(a)`, `rotation_axis(axis, a)`, `look_at_rh(eye, center, up)`, `perspective_rh_gl(fov_y, aspect, near, far)` / `orthographic_rh_gl(l, r, b, t, n, f)` (depth -1..1), `perspective_rh` / `orthographic_rh` (depth 0..1). `Matrix { rows, cols, data }` (column-major): `matrix(r, c, data)`, `from_rows([[…]])`, `zero_matrix(r, c)`, `identity(n)`; `*` by Matrix/Vector/scalar, `+`, `-`, `m[(r, c)]`, `row`, `col`, `transpose`, `determinant`, `inverse` (Gauss-Jordan, partial pivoting); shape errors are runtime errors (`matrix shapes don't fit: 2x3 * 2x3`). Fixed matrices print by rows `[(1, 0), (0, 1)]`, a `Matrix` `[[1, 0], [0, 1]]`.
- std.quaternion: `Quat { x, y, z, w }`: `from_axis_angle(axis, a)`, `from_rotation_x/y/z(a)`, `from_euler_xyz(x, y, z)` (x first), `quat(x, y, z, w)`, `Quat.identity()`. `a * b` (b first), `q * v` rotates a `Vec3`, `q * s`, `+`, `-`, `-q`. Methods: `dot`, `length`, `normalized`, `conjugate`, `inverse`, `slerp(end, t)`, `to_mat3`, `to_mat4`, `to_axis_angle -> (Vec3, S)`.
- Gotchas: radians everywhere, right-handed; `Mat4.inverse` goes through `Matrix`'s elimination; the operator methods beside others of their trait are renamed (`mul$float64`), so use the operators, not `v.mul(2.0)`.
- Prose: `docs/Language/Standard-library/Vector.md`, `Matrix.md`, `Quaternion.md`

## std.xml
Non-validating XML 1.0: tree, pull reader, stream reader, writer. `import std.xml as xml`.
- `enum XmlErrorKind { UnexpectedEnd, Expected(str), InvalidChar, InvalidName, MismatchedTag, DuplicateAttribute, InvalidReference, UndefinedEntity, LtInAttribute, InvalidComment, CDataEndInText, MisplacedDeclaration, InvalidDeclaration, UnsupportedEncoding, TextOutsideRoot, MultipleRoots, NoRoot, MisplacedMarkup, Io }` · `struct XmlError { kind, line: int, col: int }`
- `enum Node { Element(Element), Text(str), Comment(str), Pi(str, str) }` · `struct Element { name: str, attrs: [(str, str)], children: [Node] }` · `struct Declaration { version, encoding, standalone: str }` · `struct Document { declaration: Option<Declaration>, doctype: Option<str>, prolog: [Node], root: Element, epilog: [Node] }`
- `fun element(name: str, attrs: [(str, str)], children: [Node]) -> Element`: `.attr(name) -> Option<str>` · `.elements() -> [Element]` (child elements) · `.find(name) -> Option<Element>` · `.find_all(name) -> [Element]` · `.text() -> str`
- `fun parse(text: str) -> Result<Element, XmlError>` (the root) · `fun parse_document(text) -> Result<Document, XmlError>` · `fun parse_stream<R: Read>(r: R) -> Result<Document, XmlError>`
- Events: `enum Event { Declaration(Declaration), Doctype(str), Start(str, [(str, str)]), End(str), Text(str), CData(str), Comment(str), Pi(str, str), Eof }` · `fun reader(text: str) -> XmlReader` · `fun stream_reader<R: Read>(r: R) -> XmlStreamReader<R>`: `.read_event(var self) -> Result<Event, XmlError>` (stream: `.io_error() -> Option<IoError>`); both are `Iterator<Result<Event, XmlError>>`
- Write: `fun to_string(e: Element) -> str` · `fun pretty(e: Element, indent: int = 2) -> str` · `fun escape_text(s: str) -> str` · `fun escape_attr(s: str) -> str`
- Gotchas: no namespaces (`svg:rect` is the name); DOCTYPE skipped, no declared entities.

## std.yaml
Safe YAML 1.2 subset (core schema: `yes`/`no` are strings). `import std.yaml as yaml`.
- `#derive(Eq) enum Yaml { Null, Bool(bool), Int(int64), Float(float64), Str(str), List([Yaml]), Map([(str, Yaml)]) }`
- `enum YamlErrorKind { Anchor, Alias, Tag, Directive, MultipleDocuments, ExplicitKey, ComplexKey, Tab, Indentation, MissingColon, InlineCollection, MultilineKey, DuplicateKey, UnclosedQuote, InvalidEscape, UnclosedFlow, MissingComma, BlockScalarHeader, Unexpected, TooDeep, OutOfRange }` · `struct YamlError { kind, line: int, col: int }`
- `fun parse(text: str) -> Result<Yaml, YamlError>` · `fun to_string(v: Yaml) -> str` · `fun resolve(text: str) -> Yaml` (a plain scalar by the core schema) · `fun field(v: Yaml, key: str) -> Option<Yaml>` · `.as_int()`, `.as_float()`, `.as_str()`, `.as_bool()`, `.as_list() -> Option<[Yaml]>`, `.as_map() -> Option<[(str, Yaml)]>` · `fun to_json(v: Yaml) -> Json` · `fun from_json(j: Json) -> Yaml`
- Gotchas: anchors, aliases, tags, `?` keys, non-string keys and multiple documents are errors (never misread); no `#derive(Yaml)`: go through `to_json` + `json` if needed.

## lib/debug/myla_gdb.py
Not a Myla module: gdb pretty-printers for `myla build -g` binaries (strings, builders, lists, maps, float32, boxed enums). Embedded in the binary's `.debug_gdb_scripts`; run `gdb -iex 'add-auto-load-safe-path .' ./prog`, or `source lib/debug/myla_gdb.py`; `print/r x` shows the raw value.
