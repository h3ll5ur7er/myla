# std.ioerror

`IoError`, why an I/O operation failed, with `from_errno` and `io_error_name` ([[MYLA-432]]). The module imports nothing. `std.fs` re-exports all three, so `from std.fs import IoError` and `fs.IoError` name this same type, and the whole description of the causes is on [[Language/Standard-library/Fs]].

| Item | |
| --- | --- |
| `enum IoError { NotFound, PermissionDenied, …, Other(int32) }` | The cause, the same on every target (D129); `e.message()` is it in words with its name after it, and `f"{e}"` shows that (D173, D168) |
| `from_errno(code: int32) -> IoError` | The cause of a platform error code (Linux's numbers on every target) |
| `io_error_name(e: IoError) -> str` | The cause's name alone: `"NotFound"`, `"Other(9)"` |

It is a module of its own so that `std.io`, whose operations give an `IoError`, doesn't import `std.fs`, which imports `std.io`'s stream traits: a program importing `std.io` reads `std.io` and this module, not all of `std.fs` too. Modules of `std` that need only the error (`std.io`, `std.process`, `std.net`, `std.csv`, `std.xml`, `std.http`, `std.compress`, `std.archive`) import it from here. A type error names the type by this module, `ioerror.IoError`, whichever module the program imported it from.

```myla
from std.ioerror import IoError, from_errno

fun main() {
    let e = from_errno(2)
    print(f"{e}")
    match e {
        IoError.NotFound => print("missing"),
        _ => print("something else"),
    }
}
// output:
// not found (NotFound)
// missing
```
