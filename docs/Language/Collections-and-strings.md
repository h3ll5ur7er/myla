# Collections and strings

[TOC]

## Lists

```myla
fun main() {
    var xs = [3, 1, 2]
    let empty: [str] = []
    push(xs, 4)
    xs[0] = 10
    let last = pop(xs)          // 4
    print(len(xs))              // 3
    print(xs[0] + last)
    print(len(empty))
    for x in xs { print(x) }
}
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

## Maps

```myla
fun main() {
    var ages: [str: int] = [:]
    ages["ann"] = 31
    ages["bob"] = 27
    print(ages["ann"])
    print(contains(ages, "cy"))
    match get(ages, "bob") {
        Some(a) => print(a)
        None => print("unknown")
    }
    remove(ages, "bob")
    print(len(keys(ages)))
}
```

| Operation | Notes |
| --- | --- |
| `[k: v, …]`, `[:]` | Keys must be an integer type, `char`, `bool` or `str`; `[:]` needs an expected type |
| `m[k]` | A missing key is a runtime error; use `get(m, k) -> Option<V>` (a prelude function) to ask safely |
| `m[k] = v` | Inserts or replaces; needs a `var` place |
| `contains(m, k)`, `keys(m) -> [K]`, `len(m)` | |
| `remove(m, k)` | Needs a `var` place; removing a missing key does nothing |
| `for k in m` | Visits the keys in no defined order |

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

`format(fmt, args…) -> str` replaces each `{}` in `fmt` by the next argument rendered as `print` would; `{{` and `}}` are literal braces. `fmt` must be a string literal, and the number of `{}` must match the number of arguments (checked at compile time). Arguments may be integers, floats, `char`, `bool` and `str`. `f"…{expr}…"` is shorthand for `format` ([[Language/Lexical-structure]]).

How values are rendered:

- integers in decimal, unsigned ones without a sign;
- `bool` as `true`/`false`; `char` as its UTF-8 glyph;
- floats in plain positional decimal, never in exponent form: the value rounded to 9 significant digits for `float32` or 17 for `float64` (enough to read it back exactly), with trailing zeros trimmed. So `6.0` prints `6`, `0.5` prints `0.5`, but `0.1f64` prints `0.10000000000000001` and `1e20` (a `float32`) prints `100000002000000000000`. Special values print `nan`, `inf`, `-inf` and `-0`.

The interpreter and the native backend share the float algorithm and constant tables, so their output is byte-identical (D56, [[Architecture/Native-backend]]).

## StringBuilder

```myla
fun join(parts: [str], sep: str) -> str {
    var sb = StringBuilder()
    var first = true
    for p in parts {
        if !first { append(sb, sep) }
        append(sb, p)
        first = false
    }
    return build(sb)
}

fun main() {
    print(join(["a", "b", "c"], ", "))
}
```

`StringBuilder()` creates an empty builder; `append(sb, s)` and `append_byte(sb, b: uint8)` add to it (a `var` place is needed); `len(sb)` is its byte length; `build(sb)` returns a new `str`. Use it instead of `+` in loops, which copies the whole string each time.

`append(sb, s, start, end)` adds the bytes of `s` from `start` up to `end` (both `int32`), which is how to take part of a string ([[MYLA-85]]). The range must lie within `s` (`0 <= start <= end <= len(s)`), else it is a runtime error, like an index out of bounds. A range may split a multi-byte character; the bytes are kept, and joined again they make the same string.

```myla
fun substring(s: str, start: int, end: int) -> str {
    var sb = StringBuilder()
    append(sb, s, start, end)
    return build(sb)
}
```
