# Myla (Rust edition) — Standard Library

The prelude and built-in functions are always in scope. In the interpreter they
are backed by Rust's `std`. `Option` and `Result` are predeclared enums.

## Prelude types

```myla
enum Option<T> { Some(T), None }
enum Result<T, E> { Ok(T), Err(E) }
```

The `?` operator unwraps `Ok`/`Some` and early-returns `Err`/`None`.

## Core builtins

| Function | Signature (informal) | Notes |
| --- | --- | --- |
| `print(x)` | `(any) -> unit` | Prints a value and a newline. |
| `eprint(x)` / `eprintln(x)` | `(any) -> unit` | Write to stderr. |
| `format(fmt, args...)` | `(str, ...) -> str` | `{}` holes, `{{`/`}}` escapes. |
| `len(x)` | `(list \| map \| str \| tuple) -> int` | Length / byte length. |
| `abs(x)` | `(int \| float) -> same` | Absolute value. |
| `assert(cond [, msg])` | `(bool [, str]) -> unit` | Traps if false. |
| `panic(msg)` | `(str) -> never` | Aborts with a runtime error. |
| `unreachable()` | `() -> never` | Marks impossible code. |
| `exit(code)` | `(int) -> never` | Exits the process. |

## Collections

Method forms on lists/maps/strings (the receiver of `xs.push(..)` etc. must be a
`var` binding for mutating methods):

- **List:** `push(x)`, `pop() -> Option<T>`, `get(i) -> Option<T>`,
  `contains(x) -> bool`, `map(f) -> [U]`, `filter(f) -> [T]`, `len()`.
- **Map:** `insert(k, v)`, `remove(k) -> Option<V>`, `get(k) -> Option<V>`,
  `contains(k) -> bool`, `keys() -> [K]`, `values() -> [V]`, `len()`.
  Keys may be any value (structs, tuples, strings, enums).
- **Str:** `len()`, `chars() -> [char]`, `contains(s)`, `starts_with(s)`,
  `ends_with(s)`, `to_upper()`, `to_lower()`, `trim()`, `split(sep) -> [str]`.
- Indexing: `xs[i]`, `m[k]`, `s[i]` (byte), `t[i]` (tuple element).
  `m[k] = v` inserts/updates a map entry.

## I/O, filesystem, process, time

| Function | Returns |
| --- | --- |
| `read_file(path)` | `Result<str, str>` |
| `write_file(path, content)` | `Result<unit, str>` |
| `append_file(path, content)` | `Result<unit, str>` |
| `file_exists(path)` | `bool` |
| `remove_file(path)` | `Result<unit, str>` |
| `read_line()` | `Option<str>` (stdin) |
| `run(cmd, [args])` | `Result<str, str>` (captures stdout) |
| `args()` | `[str]` (program arguments) |
| `env_var(name)` | `Option<str>` |
| `now_millis()` | `int64` (Unix epoch ms) |
| `sleep_millis(ms)` | `unit` |
| `str_to_int(s)` | `Option<int>` |
| `int_to_str(n)` | `str` |

## Concurrency

`make_chan()` constructs a channel; see [concurrency.md](concurrency.md) for
`spawn`/`go`, `send`/`recv`/`try_recv`, `select`, `async`/`await`, and actors.

## Operator overloading

User types participate in operators by implementing methods named after the
operation: `add`, `sub`, `mul`, `div`, `rem` for arithmetic, and `cmp`
(returning an ordering `int`: negative / zero / positive) for `< <= > >=`.
Equality (`==`/`!=`) is structural for every value automatically.

```myla
struct Vec2 { x: int, y: int }
impl Vec2 {
    fun add(self, other: Vec2) -> Vec2 {
        return Vec2 { x: self.x + other.x, y: self.y + other.y }
    }
}
// now `a + b` works for Vec2
```
