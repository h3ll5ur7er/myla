# std.ioerror

`IoError`, why an I/O operation failed, with the cause codes the standard library's primitives give and `from_cause`, `from_errno`, `code_number` and `io_error_name` ([[MYLA-432]], D209). The module imports nothing. `std.fs` re-exports `IoError`, `from_errno` and `io_error_name`, so `from std.fs import IoError` and `fs.IoError` name this same type, and the whole description of the causes is on [[Language/Standard-library/Fs]].

| Item | |
| --- | --- |
| `enum IoError { NotFound, PermissionDenied, …, Other(int32) }` | The cause, the same on every target (D129); `e.message()` is it in words with its name after it, and `f"{e}"` shows that (D173, D168). It derives `Eq` ([[MYLA-716]]): two are equal when they are the same cause, an `Other` of the same number, so an error type can hold one (`SpawnError.WorkingDir`) |
| `from_cause(code: int32) -> IoError` | The cause of the (nonzero) cause code a primitive left (`__io_errno()`, below) |
| `code_number(code: int32) -> int32` | The number an error type's `Other` shows for a cause code: the system's own code past `OTHER`, else the one std gives the cause on every target (Linux's errno) |
| `from_errno(code: int32) -> IoError` | The cause of a **Linux** errno, on every target, for a program that holds one (read from a file, a log or another program's output). Nothing in std calls it: a primitive gives a cause code (`from_cause`), and on Windows a system's code is Windows' own, which this doesn't read |
| `io_error_name(e: IoError) -> str` | The cause's name alone: `"NotFound"`, `"Other(9)"` |
| `NOT_FOUND`, `PERMISSION_DENIED`, … `INVALID_DATA`, `WOULD_BLOCK`, `IN_PROGRESS`, `BAD_HANDLE`, `NOT_A_TERMINAL`, `TOO_MANY_OPEN`, `TOO_MANY_OPEN_SYSTEM`, `OTHER` | The cause codes (`int32`) |

## Cause codes

The primitives under `std.io`, `std.fs`, `std.process`, `std.net`, `std.term` and `std.signal` leave a cause code for `__io_errno()` (and `__run_errno()`, and a spawn's first word), never a system's own number (D209, [[MYLA-701]]). Each platform module (`std.platform`, one per target) maps its system's codes onto them, so nothing above it knows Linux's errnos, WASI's or Windows': 1 to 21 are `IoError`'s causes in its order (`NOT_FOUND` 1 … `INVALID_DATA` 21); 32 to 37 those `std.rt`, `std.net` and `std.http` act on themselves (`WOULD_BLOCK`: the operation would wait; `IN_PROGRESS`: a non-blocking connect goes on; `BAD_HANDLE`: no such open descriptor or handle; `NOT_A_TERMINAL`; `TOO_MANY_OPEN` and `TOO_MANY_OPEN_SYSTEM`: no descriptor or handle left, the process's or the system's, after which std.http's server accepts again a little later, [[MYLA-716]]), which an `IoError` shows as `Other` of the number std gives them on every target (`Other(11)`, `Other(115)`, `Other(9)`, `Other(25)`, `Other(24)`, `Other(23)`: Linux's, as before D209); a code from `OTHER` (256) on is `OTHER` plus the system's own code, `Other(code)`.

## System codes

What an `Other` holds past the causes is the system's own number, not portable to read (D129, D219): Linux's errno on Linux; on wasm32 WASI's errno as Linux's of the same name ([[MYLA-426]]), so a program's `Other`s read as on Linux; on Windows Windows' own code ([[MYLA-716]]): a full disk is `Other(112)` (`ERROR_DISK_FULL`) where Linux's is `Other(28)` (ENOSPC), and a Winsock error its `WSAE…` number. Where a platform module finds an error itself that its system names, it gives the system's code for it (a name longer than 255 units is `Other(206)`, `ERROR_FILENAME_EXCED_RANGE`, on Windows and `Other(36)` on Linux); an error std makes up above the platform keeps std's number on every target (`Other(9)` a closed handle, `Other(27)` a memory stream past its limit, `Other(10)` a child already reaped).

The words for a system's code are `std.system_error`'s `error_text(n)`, a module per target as `std.path_style` is (`std/system_error_windows.my` on Windows, which the loader takes for `std/system_error.my`): what `strerror` says on Linux and wasm32 (`no space left on device`, `input/output error`, `file too large`, `disk quota exceeded`, else `errno 71`), what Windows' own message says on Windows (`there is not enough space on the disk`, `the disk is full`, …, else `Windows error 1392`). A failed write that ends the program says them ([[Language/Standard-library/Io]]'s `errno_text`, the runtime's `write failed:`). `std.platform` has the same codes as `int64` constants of the same names, and `tests/burn/test_platform_interface.py` holds the two, and every platform module, to one numbering.

It is a module of its own so that `std.io`, whose operations give an `IoError`, doesn't import `std.fs`, which imports `std.io`'s stream traits: a program importing `std.io` reads `std.io` and this module, not all of `std.fs` too. Modules of `std` that need only the error (`std.io`, `std.process`, `std.net`, `std.csv`, `std.xml`, `std.http`, `std.compress`, `std.archive`) import it from here. A type error names the type by this module, `ioerror.IoError`, whichever module the program imported it from.

```myla
from std.ioerror import IoError, from_cause, from_errno, NOT_FOUND

fun main() {
    let e = from_cause(NOT_FOUND)
    print(f"{e}")
    match from_errno(2) {
        IoError.NotFound => print("missing"),
        _ => print("something else"),
    }
}
// output:
// not found (NotFound)
// missing
```
