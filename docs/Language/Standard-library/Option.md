# std.option

Methods on the prelude's `Option<T>` and `Result<T, E>` ([[MYLA-324]], D164): Rust's combinators, with Rust's names. Every one takes `self` and gives a new value; none changes its receiver. A function argument is called at most once, and only when the value is the one it is for: `unwrap_or_else`'s fallback runs only for a `None`, `map`'s function only for a `Some` or an `Ok`.

```myla
import std.option
from std.num import parse_int

fun port(text: str) -> Result<int64, str> {
    return parse_int(text).ok_or(f"'{text}' is not a number")
}

fun main() {
    print(port("8080").unwrap_or(80))
    print(port("eighty").err().unwrap_or(""))
    let doubled = parse_int("21").map((n: int64) => n * 2)
    print(doubled.expect("a number"))
    print(parse_int("x").is_none())
}
// output:
// 8080
// 'eighty' is not a number
// 42
// true
```

## Option

| Method | Result |
| --- | --- |
| `o.map(f: (T) -> U) -> Option<U>` | `Some(f(v))` for a `Some(v)`, `None` for a `None` |
| `o.and_then(f: (T) -> Option<U>) -> Option<U>` | `f(v)` for a `Some(v)`, `None` for a `None`: a chain of steps that may each find nothing |
| `o.or_else(f: () -> Option<T>) -> Option<T>` | `o` itself if it is a `Some`, else `f()` |
| `o.unwrap_or(default: T) -> T` | The value, or `default` for a `None` |
| `o.unwrap_or_else(f: () -> T) -> T` | The value, or `f()` for a `None`: for a fallback that costs |
| `o.ok_or(err: E) -> Result<T, E>` | `Ok(v)` for a `Some(v)`, `Err(err)` for a `None` |
| `o.is_some() -> bool`, `o.is_none() -> bool` | Which of the two it is |
| `o.expect(msg: str) -> T` | The value; a `None` fails with `msg`, as `panic(msg)` does |

## Result

| Method | Result |
| --- | --- |
| `r.map(f: (T) -> U) -> Result<U, E>` | `Ok(f(v))` for an `Ok(v)`; an `Err` stays as it is |
| `r.map_err(f: (E) -> F) -> Result<T, F>` | `Err(f(e))` for an `Err(e)`; an `Ok` stays as it is: an error made the caller's own before a `?`, which converts none |
| `r.and_then(f: (T) -> Result<U, E>) -> Result<U, E>` | `f(v)` for an `Ok(v)`; an `Err` stays as it is |
| `r.unwrap_or(default: T) -> T` | The `Ok`'s value, or `default` for an `Err` |
| `r.ok() -> Option<T>`, `r.err() -> Option<E>` | The `Ok`'s value or the `Err`'s error, as an `Option` |
| `r.is_ok() -> bool`, `r.is_err() -> bool` | Which of the two it is |
| `r.expect(msg: str) -> T` | The `Ok`'s value; an `Err` fails with `msg`. Unlike Rust's, the message doesn't show the error, which may have no `Format` |

## Notes

- **Lambdas:** a lambda passed to `map`, `and_then` or `map_err` takes its parameter's type from the receiver, `o.map((n) => n * 2)`, though the method's own type parameter (`U`, `F`) is still open ([[MYLA-356]]); the result fixes it. Writing the type, `(n: int64) => n * 2`, works too.
- **A bare `Ok(v)` or `Err(e)` as the receiver** needs its other type from an annotation (`let r: Result<int, str> = Ok(8)`), as it does anywhere else; a bare `Some(v)` doesn't.
- `match`, `if let` and `?` stay the ways to take an `Option` or a `Result` apart where a value of each case is needed ([[Language/Types]]).
