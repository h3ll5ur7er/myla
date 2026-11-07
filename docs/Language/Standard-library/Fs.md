# std.fs

The file system: whole files and directories.

| Function | Result |
| --- | --- |
| `read_to_string(path: str) -> Result<str, IoError>` | The whole file |
| `write_to_file(path: str, contents: str) -> Result<(), IoError>` | Creates or truncates (mode 0644); `Ok(())` once every byte is written (D138) |
| `list_dir(path: str) -> Result<[str], IoError>` | The names of the directory's entries, without `.` and `..`, sorted by their bytes |
| `make_dir(path: str) -> Result<(), IoError>` | Makes one directory (mode 0755 less the umask); its parent must exist |
| `make_dir_all(path: str) -> Result<(), IoError>` | Makes the directory and the parents it lacks, like `mkdir -p`; an existing directory is fine |
| `exists(path: str) -> bool` | Whether the path names anything (symbolic links followed, so a dangling one doesn't count) |
| `is_dir(path: str) -> bool`, `is_file(path: str) -> bool` | Whether it names a directory, a regular file (links followed) |
| `current_dir() -> Result<str, IoError>` | The working directory: an absolute path without symbolic links, as the kernel gives it; a directory that was removed is `NotFound` ([[MYLA-98]]) |
| `remove_file(path: str) -> Result<(), IoError>` | Removes a file, or a symbolic link itself; a directory is `IsADirectory` ([[MYLA-96]]) |
| `remove_dir(path: str) -> Result<(), IoError>` | Removes an empty directory; one that isn't is `NotEmpty` |
| `remove_dir_all(path: str) -> Result<(), IoError>` | Removes the path and, for a directory, everything in it, like `rm -r`; symbolic links are removed, not followed |
| `rename(from_path: str, to: str) -> Result<(), IoError>` | Renames or moves within one file system, replacing a file at `to` |
| `enum IoError { NotFound, PermissionDenied, AlreadyExists, NotADirectory, IsADirectory, NotEmpty, Interrupted, Cancelled, Unsupported, BrokenPipe, InvalidInput, Other(int32) }` | Why an operation failed, the same causes on every target (D129); `Cancelled`: a task's read stopped by `task.cancel` or a timeout (D96); `Unsupported`: the target can't do it; `BrokenPipe`: a write to a pipe nobody reads any more (D146); `InvalidInput`: a path with a NUL byte in it, which names nothing; `PermissionDenied` is EACCES and EPERM both; `Other` holds the platform's own code for anything else, whose numbers aren't portable |

The file's bytes become the string unchanged, even when they aren't valid UTF-8: strings work on bytes, and `chars` gives U+FFFD for the invalid ones ([[Language/Collections-and-strings]], [[MYLA-12]]).

`from_errno(code: int32) -> IoError` turns the platform layer's code (Linux's numbers on every target so far; wasm32's maps WASI's onto them) into its cause; `std.io` and `std.process` use it too.

```myla
from std.fs import list_dir, make_dir_all, is_dir, IoError

fun main() {
    match make_dir_all("build/out") {
        Ok(n) => {},
        Err(e) => { print("could not make build/out") },
    }
    match list_dir("src") {
        Ok(names) => {
            for n in names {
                if is_dir("src/" + n) { print(n + "/") } else { print(n) }
            }
        },
        Err(e) => { print("no src directory") },
    }
}
// output:
// no src directory
```

## Directory primitives

The directory functions rest on seven primitives (D64's pattern: a small system call per implementation, the rest shared Myla code; [[MYLA-88]], [[MYLA-98]], [[MYLA-96]]):

| Primitive | Does | Result |
| --- | --- | --- |
| `__list_dir(path: str) -> str` | open(2) with `O_DIRECTORY`, getdents64(2) until the end, close(2) | Every name the directory lists, each followed by a NUL byte, in the file system's order (`.` and `..` may be among them); `""` on an error |
| `__mkdir(path: str, mode: int32)` | mkdir(2) | Nothing |
| `__stat(path: str) -> int32` | stat(2) | `st_mode` (file type and permission bits), or -1 on an error |
| `__getcwd() -> str` | getcwd(2) into a 4 KB buffer | The working directory, or `""` on an error (ENOENT for a removed directory, ERANGE for a path longer than the buffer) |
| `__unlink(path: str)` | unlink(2) | Nothing (a directory is EISDIR, which `remove_dir_all` uses to tell one without following links) |
| `__rmdir(path: str)` | rmdir(2) | Nothing |
| `__rename(from: str, to: str)` | rename(2) | Nothing |

The system calls named are x86-64 Linux's; aarch64 uses the generic `*at` forms (`openat`, `mkdirat`, `unlinkat`, `renameat2`), wasm32 WASI's (`path_open`, `fd_readdir`, …), translated into the same results. Each sets the errno that `__io_errno()` reads (0 on success), a Linux number on every target (WASI's are mapped onto them). A name can't hold a NUL byte, so NUL separates them. `list_dir` drops `.` and `..` and sorts the names by their bytes, so every file system gives the same list (and the Python interpreter, with `os.listdir`, gave it too).

## Descriptor and entropy primitives

Files opened and read or written a piece at a time, at a cursor, and the system's entropy rest on these ([[MYLA-336]], D64's pattern again; the API over them is [[MYLA-339]]'s `File` and [[MYLA-337]]'s `std.random`). A descriptor is an `int`; `__read(fd, n)` (one read of up to `n` bytes at the cursor, `""` at the end), `__write(fd, s)` (every byte of `s` at the cursor, again after a short write) and `__close(fd)` are the ones `std.io` and `std.process` already use.

| Primitive | Does | Result |
| --- | --- | --- |
| `__open(path: str, flags: int, mode: int) -> int` | open(2) with `O_CLOEXEC`; `flags` are Myla's own bits, the same on every target: 1 read, 2 write (both: read and write), 4 create, 8 truncate, 16 append (each write at the end, wherever the cursor is), 32 exclusive (with create: EEXIST when the file is there) | The descriptor, or -1. Without 1 or 2, with another bit, or a NUL in the path: EINVAL. `mode` is the permissions of a file it creates, less the umask |
| `__seek(fd: int, offset: int64, whence: int) -> int64` | lseek(2): `offset` from the start (`whence` 0), the cursor (1) or the end (2) | The new offset from the start, or -1 (EINVAL for another whence or a place before the start, ESPIPE for a pipe) |
| `__fstat(fd: int) -> [int64]` | fstat(2) | `[size, mode, mtime]`: the size in bytes, the mode as `__stat` gives it (type bits and permissions), the modification time in nanoseconds since 1970; `[]` on an error |
| `__random_bytes(n: int) -> [uint8]` | getrandom(2) until `n` bytes are there (a call gives at most 32 MB, and a signal may cut one of 256 bytes or more short) | `n` bytes; `[]` on an error (EINVAL for a negative `n`) |

aarch64 opens with `openat`; wasm32 uses `path_open` (the flags as its open flags, rights and `FDFLAGS_APPEND`), `fd_seek`, `fd_filestat_get` and `random_get`. WASI has no permissions: `mode` is not used there, and the mode `__fstat` gives is made up from the file's kind, as `__stat`'s is (0o100644 for a file, 0o40755 for a directory, 0o644 for anything else). Each sets `__io_errno()` as the directory primitives do; the interpreter calls the same primitives of its own.
