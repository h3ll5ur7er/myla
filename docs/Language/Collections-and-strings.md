# Collections and strings

[TOC]

## Lists

```myla
fun main() {
    var xs = [3, 1, 2]
    let empty: [str] = []
    xs.push(4)
    xs[0] = 10
    let last = xs.pop()          // 4
    print(xs.len())              // 3
    print(xs[0] + last)
    print(empty.len())
    for x in xs { print(x) }
}
// output:
// 3
// 14
// 0
// 10
// 1
// 2
```

| Operation | Notes |
| --- | --- |
| `[a, b, c]` | Elements unify to one type; an expected element type flows into the literals (`let b: [uint8] = [1, 2]`) |
| `[]` | Needs an expected type |
| `len(xs)` | `int` |
| `xs[i]` | Any integer index; out of bounds is a runtime error |
| `xs[i] = v` | Needs a `var` place |
| `push(xs, v)`, `pop(xs)` | Built-in functions (not methods); need a `var` place; `pop` returns the last element, and popping an empty list is a runtime error |
| `for x in xs` | Visits a snapshot of the elements |

## Slices and indexes from the end

`^n` counts from the end, in an index and in a slice's bounds: `xs[^1]` is the last element (D142, [[MYLA-280]]). A slice `xs[a:b]` is a new list of the elements from `a` up to, not including, `b`; `xs[a:]`, `xs[:b]` and `xs[:]` leave a bound out, and `xs[a:b:step]` takes every `step`-th, backwards for a negative step.

```myla
fun main() {
    let xs = [10, 20, 30, 40, 50]
    print(xs[^1])
    print(xs[1:^1].len())
    print(xs[::-1][0])
    print(xs[2:99].len())
    let s = "hello, world"
    print(s[7:])
    print(s[::-1])
}
// output:
// 50
// 3
// 50
// 3
// world
// dlrow ,olleh
```

- A slice's bounds are clamped to the list, so a slice never fails: `xs[2:99]` is the rest, `xs[5:2]` is empty, and a plain negative bound is before the start (only `^` counts from the end). A single index out of range is still an error, `xs[^0]` and `xs[^6]` of five elements too (D143).
- The step is a signed integer, not 0 (`slice step is zero` when the program runs). With a negative step the bounds left out are the end and the start, as in Python: `xs[^1:0:-2]` is `[50, 30]`.
- A `str` is sliced by bytes, as `s[i]` and `len(s)` count them: a slice whose bound falls inside a character is a runtime error (`a slice bound inside a character`), and with a step other than 1 every byte taken must be a whole character (ASCII).
- `xs[^1] = v` assigns as any index does; a slice is a value to read: assigning to one (`xs[1:3] = ys`) isn't part of the language yet. Maps have no slices.

## Maps

```myla
fun main() {
    var ages: [str: int] = [:]
    ages["ann"] = 31
    ages["bob"] = 27
    print(ages["ann"])
    print(ages.contains("cy"))
    match get(ages, "bob") {
        Some(a) => print(a)
        None => print("unknown")
    }
    ages.remove("bob")
    print(ages.keys().len())
}
// output:
// 31
// false
// 27
// 1
```

| Operation | Notes |
| --- | --- |
| `[k: v, …]`, `[:]` | Keys must be an integer type, `char`, `bool` or `str`; `[:]` needs an expected type |
| `m[k]` | A missing key is a runtime error; use `get(m, k) -> Option<V>` (a prelude function) to ask safely |
| `m[k] = v` | Inserts or replaces; needs a `var` place |
| `m.contains(k)`, `m.keys() -> [K]`, `m.len()` | `keys` gives the keys in the order `for` visits them |
| `m.remove(k)` | Needs a `var` place; removing a missing key does nothing |
| `for k in m` | Visits the keys in the order they were first inserted: replacing a value keeps its key's place, removing a key and inserting it again moves it to the end (D105, [[MYLA-179]]) |

## Methods of the builtin types

The builtin collection and string functions are methods of their first argument (D103, [[MYLA-221]]): `xs.push(v)` is `push(xs, v)`.

| Method | Of |
| --- | --- |
| `len()` | lists, maps, strings, `StringBuilder` |
| `push(v)`, `pop()` | lists (a `var` place) |
| `contains(k)`, `keys()`, `remove(k)` | maps (`remove`: a `var` place) |
| `chars()` | strings |
| `append(s)`, `append(s, start, end)`, `append_byte(b)`, `build()` | `StringBuilder` (`append`, `append_byte`: a `var` place) |

A type's own method of the same name (`impl str { fun len(self) … }`) comes first, and a local named `chars` doesn't hide `s.chars()`. The function forms still work while the repository moves to the methods; then they go (D103).

## Value semantics and copy-on-write

Lists, maps and builders behave like every other value: `let b = a` makes an independent copy, and changing `b` never changes `a` (D38). Natively a copy shares the heap cell and bumps its reference count; the first write through a copy whose cell is shared clones the cell first. A `let` list can't be changed at all, not even its elements (D14).

## Strings

`str` is an immutable sequence of bytes, normally UTF-8 (D21, D42). A string read from a file or built with `append_byte` can hold any bytes; every operation below works on the bytes, and `print` writes them unchanged ([[MYLA-12]]).

| Operation | Result |
| --- | --- |
| `len(s)` | Number of **bytes** |
| `s[i]` | The byte at `i`, as a `uint8`; out of bounds is a runtime error; strings can't be assigned into |
| `a + b` | A new string |
| `a == b`, `a != b` | Byte-wise equality; there is no `<` on strings |
| `chars(s)` | `[char]`, one element per Unicode scalar; each byte that isn't part of a well-formed UTF-8 sequence (a stray or truncated byte, an overlong form, an encoded surrogate) gives U+FFFD |
| `format("{} of {}", a, b)` | See below |

Byte comparisons with ASCII char literals type-check directly: `if s[i] == ' ' { … }`.

## format and f-strings

`format(fmt, args…) -> str` replaces each `{}` in `fmt` by the next argument rendered as `print` would (or as a spec says, `{:>8}`, below); `{{` and `}}` are literal braces. `fmt` must be a string literal, and the number of `{}` must match the number of arguments (checked at compile time). Arguments may be integers, floats, `char`, `bool` and `str`. `f"…{expr}…"` is shorthand for `format` ([[Language/Lexical-structure]]).

How values are rendered:

- integers in decimal, unsigned ones without a sign;
- `bool` as `true`/`false`; `char` as its UTF-8 glyph;
- floats in plain positional decimal, never in exponent form: the value rounded to 9 significant digits for `float32` or 17 for `float64` (enough to read it back exactly), with trailing zeros trimmed. So `6.0` prints `6`, `0.5` prints `0.5`, but `0.1f64` prints `0.10000000000000001` and `1e20` (a `float32`) prints `100000002000000000000`. Special values print `nan`, `inf`, `-inf` and `-0`.

### Format specs

A hole may carry a spec after a `:`, `{x:spec}` in an f-string or `{:spec}` in `format`'s string (D139, [[MYLA-277]]). It is Rust's: `[[fill]align][sign][#][0][width][.precision][kind]`, checked against the value's type when the program is compiled.

```myla
fun main() {
    let pi = 3.14159265
    print(f"{pi:.2} [{42:>6}] [{42:<6}] [{"ab":^6}] {7:03} {-7:04} {7:+}")
    print(f"{255:x} {255:X} {255:b} {255:o} {255:#06x} {5:08b} {-1i8:x}")
    print(f"{2.675:.2} {0.125:.2} {2.5:.0} [{3.5:*>8.2}]")
}
// output:
// 3.14 [    42] [42    ] [  ab  ] 007 -007 +7
// ff FF 11111111 377 0x00ff 00000101 ff
// 2.67 0.12 2 [****3.50]
```

| Part | Meaning | On |
| --- | --- | --- |
| `fill` `align` | `<` left, `>` right, `^` centred, after an optional fill character (a space by default); numbers align right and text left unless the spec says otherwise | every printable type |
| `width` | the least number of characters (Unicode scalars); a longer value is never cut | every printable type |
| `+` | a sign on a value that isn't negative | integers, floats |
| `#` | the prefix of a kind, `0x`, `0b` or `0o`, counted in the width | integers with a kind |
| `0` | zeros between the sign (and prefix) and the digits, up to the width | integers, floats |
| `.precision` | that many digits after the point, rounded on the exact binary value to nearest, ties to even: `2.675` (2.67499… in binary) gives `2.67`, `0.125` gives `0.12` | floats |
| `kind` | `x` `X` hexadecimal, `b` binary, `o` octal; a negative signed value as its two's complement at its type's width (`{-1i8:x}` is `ff`) | integers |

Anything else is a compile-time error at the value: `the format spec '.2' needs a float, found 'int32'`, `invalid format spec 'q'`. A hole's spec may not contain `{` or `}`.

A type of the program can give itself a form by implementing the prelude's `Format` trait: `{x}` calls `x.format("")`, `{x:spec}` passes the spec's text as it is, read when the program runs (it isn't checked before), and `std.fmt.pad(text, spec)` applies fill, alignment and width ([[Language/Standard-library]]).

```myla
import std.fmt as fmt

struct Date {
    y: int,
    m: int,
    d: int,
}

impl Format for Date {
    fun format(self, spec: str) -> str {
        return match spec {
            "" => f"{self.y:04}-{self.m:02}-{self.d:02}"
            "dmy" => f"{self.d:02}.{self.m:02}.{self.y}"
            _ => fmt.pad(self.format(""), spec)
        }
    }
}

fun main() {
    let d = Date { y: 2026, m: 11, d: 5 }
    print(f"{d} {d:dmy} [{d:>12}]")
}
// output:
// 2026-11-05 05.11.2026 [  2026-11-05]
```

`print(x)` still takes the five scalar types: a struct goes through `print(f"{x}")`.

The interpreter and the native backend share the float algorithm and constant tables, so their output is byte-identical (D56, [[Architecture/Native-backend]]).

## StringBuilder

```myla
fun join(parts: [str], sep: str) -> str {
    var sb = StringBuilder()
    var first = true
    for p in parts {
        if !first { sb.append(sep) }
        sb.append(p)
        first = false
    }
    return sb.build()
}

fun main() {
    print(join(["a", "b", "c"], ", "))
}
// output:
// a, b, c
```

`StringBuilder()` creates an empty builder (it takes no arguments); `append(sb, s)` and `append_byte(sb, b: uint8)` add to it (a `var` place is needed); `len(sb)` is its byte length; `build(sb)` returns a new `str`. Use it instead of `+` in loops, which copies the whole string each time.

`append(sb, s, start, end)` adds the bytes of `s` from `start` up to `end` (both `int32`), which is how to take part of a string ([[MYLA-85]]). The range must lie within `s` (`0 <= start <= end <= len(s)`), else it is a runtime error, like an index out of bounds. A range may split a multi-byte character; the bytes are kept, and joined again they make the same string.

```myla
fun substring(s: str, start: int, end: int) -> str {
    var sb = StringBuilder()
    sb.append(s, start, end)
    return sb.build()
}
```
