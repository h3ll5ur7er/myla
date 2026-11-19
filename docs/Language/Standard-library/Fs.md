# std.fs

The file system: whole files, files read and written a piece at a time, metadata, temporary files and directories.

| Function | Result |
| --- | --- |
| `read_to_string(path: str) -> Result<str, IoError>` | The whole file |
| `write_to_file(path: str, contents: str) -> Result<(), IoError>` | Creates or truncates (mode 0644); `Ok(())` once every byte is written (D138) |
| `read_bytes(path: str) -> Result<[uint8], IoError>`, `write_bytes(path: str, b: [uint8]) -> Result<(), IoError>` | The same in bytes ([[MYLA-420]], [[MYLA-339]]'s follow-up) |
| `list_dir(path: str) -> Result<[str], IoError>` | The names of the directory's entries, without `.` and `..`, sorted by their bytes |
| `make_dir(path: str) -> Result<(), IoError>` | Makes one directory (mode 0755 less the umask); its parent must exist |
| `make_dir_all(path: str) -> Result<(), IoError>` | Makes the directory and the parents it lacks, like `mkdir -p`; an existing directory is fine |
| `exists(path: str) -> bool` | Whether the path names anything (symbolic links followed, so a dangling one doesn't count) |
| `is_dir(path: str) -> bool`, `is_file(path: str) -> bool` | Whether it names a directory, a regular file (links followed) |
| `is_symlink(path: str) -> bool` | Whether it names a symbolic link itself, a dangling one too ([[MYLA-363]]) |
| `read_link(path: str) -> Result<str, IoError>` | What the symbolic link holds: the path it leads to as written in it (relative to the link's directory, or absolute), not followed; a path that is no link is `InvalidInput`, a missing one `NotFound` ([[MYLA-841]]) |
| `canonical(path: str) -> Result<str, IoError>` | The absolute path of what it names without a symbolic link, `.` or `..` (realpath(3)): each link on the way followed, a relative one from its own directory; a missing part is `NotFound`, a part that isn't a directory before the end `NotADirectory`, more than 40 links (a loop) `Other(40)` (ELOOP) on every target ([[MYLA-841]]) |
| `current_dir() -> Result<str, IoError>` | The working directory: an absolute path without symbolic links, as the kernel gives it; a directory that was removed is `NotFound` ([[MYLA-98]]) |
| `remove_file(path: str) -> Result<(), IoError>` | Removes a file, or a symbolic link itself; a directory is `IsADirectory` ([[MYLA-96]]) |
| `remove_dir(path: str) -> Result<(), IoError>` | Removes an empty directory; one that isn't is `NotEmpty` |
| `remove_dir_all(path: str) -> Result<(), IoError>` | Removes the path and, for a directory, everything in it, like `rm -r`; symbolic links are removed, not followed |
| `rename(from_path: str, to: str) -> Result<(), IoError>` | Renames or moves within one file system, replacing a file at `to` |
| `enum IoError { NotFound, PermissionDenied, AlreadyExists, NotADirectory, IsADirectory, NotEmpty, Interrupted, Cancelled, Unsupported, BrokenPipe, InvalidInput, ConnectionRefused, ConnectionReset, ConnectionAborted, NotConnected, AddrInUse, AddrNotAvailable, TimedOut, HostUnreachable, NetworkUnreachable, InvalidData, Other(int32) }` | Why an operation failed, the same causes on every target (D129); the network's causes are `std.net`'s ([[MYLA-346]], [[Language/Standard-library/Net]]); `Cancelled`: a task's read stopped by `task.cancel` or a timeout (D96); `Unsupported`: the target can't do it; `BrokenPipe`: a write to a pipe nobody reads any more (D146); `InvalidInput`: a path with a NUL byte in it, which names nothing; `PermissionDenied` is EACCES and EPERM both; `Other` holds the platform's own code for anything else, whose numbers aren't portable (a few are std's own, the same everywhere: `Other(9)` a handle that isn't open, `Other(11)` an operation that would wait, D209) |

The file's bytes become the string unchanged, even when they aren't valid UTF-8: strings work on bytes, and `chars` gives U+FFFD for the invalid ones ([[Language/Collections-and-strings]], [[MYLA-12]]).

The primitives under this module leave a cause code for `__io_errno()`, never a system's number (D209): each platform module maps its own system's codes onto std.ioerror's causes, which `from_cause` turns into an `IoError` ([[Language/Standard-library/Ioerror]]). `from_errno(code: int32) -> IoError` gives the cause of a Linux errno, on every target, for a program that holds one (nothing in std calls it; on Windows a system's code is Windows' own, [[MYLA-716]]). `IoError`, `from_errno` and `io_error_name` are [[Language/Standard-library/Ioerror|std.ioerror]]'s, which this module re-exports, so that `std.io` needn't import `std.fs` ([[MYLA-432]]); `std.io`, `std.process` and `std.net` use them too. `e.message()` is the cause in words with its name after it (D173, [[MYLA-379]]): `not found (NotFound)`, `permission denied (PermissionDenied)`, `connection refused (ConnectionRefused)`, `error 5 (Other(5))` with the platform's code. `IoError` implements `Format` by it, so `f"{e}"`, `print(e)` and a test function's report (`FAIL  reads_the_config: not found (NotFound)`) show that text (D168). `io_error_name(e: IoError) -> str` is the cause's name alone, its variant's (`"NotFound"`, `"Other(9)"`), by which the error messages of std.compress, std.archive and std.http name an `IoError` ([[MYLA-376]]).

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
        Err(e) => { print(f"no src directory: {e}") },
    }
}
// output:
// no src directory: not found (NotFound)
```

## Files

A `File` is an open file, read and written at its cursor a piece at a time, so a file bigger than memory goes through in pieces ([[MYLA-339]]). It is a stream of `std.io` ([[Language/Standard-library/Io#streams]]): it implements `Read`, `Write` and `Seek` (and `Pollable`), so `buffered`, `buffered_writer`, `copy` and `read_all` take it. It buffers nothing: each `read` and `write` is a system call, and a `Buffered` or `BufferedWriter` in front of it gathers small pieces.

| Item | Result |
| --- | --- |
| `open(path: str) -> Result<File, IoError>` | The file, open for reading |
| `create(path: str) -> Result<File, IoError>` | The file, open for writing: created (mode 0644 less the umask) or emptied |
| `open_append(path: str) -> Result<File, IoError>` | The file, open for appending: created when it isn't there, and every write goes to its end, wherever the cursor is |
| `options() -> OpenOptions` | Options that choose nothing yet, for any other way: `options().read(true).write(true).create(true).open(path)` |
| `o.read(on)`, `o.write(on)`, `o.append(on)`, `o.truncate(on)`, `o.create(on)`, `o.create_new(on)` | The options with one choice changed: to read; to write at the cursor; to write at the end (it writes, too); to empty the file; to create it when it isn't there; to create it and fail with `AlreadyExists` when it is (one step, so no other program comes in between) |
| `o.mode(perms: int32) -> OpenOptions` | The permissions of a file it creates (0644 unless chosen; less the umask) |
| `o.open(path: str) -> Result<File, IoError>` | The file, opened as chosen; neither reading nor writing is `InvalidInput` |
| `f.read(n: int) -> Result<[uint8], IoError>` | One read of up to `n` bytes at the cursor; `[]` at the end (`Read`) |
| `f.write(b: [uint8]) -> Result<int, IoError>` | All the bytes at the cursor, their count (`Write`) |
| `f.flush() -> Result<(), IoError>` | Nothing to do, as nothing is buffered: `Ok(())` (`Write`) |
| `f.seek(pos: SeekFrom) -> Result<int64, IoError>` | The cursor moved: `SeekFrom.Start(k)`, `Current(k)`, `End(k)`; the new offset. Before the start is `InvalidInput` (`Seek`) |
| `f.len() -> Result<int64, IoError>` | The file's size in bytes now |
| `f.metadata() -> Result<Metadata, IoError>` | Its size, kind, permissions and modification time now |
| `f.close() -> Result<(), IoError>` | Closes it; every later operation on it, a second `close` too, is `Other(9)` (EBADF). What the system couldn't keep of the data written is `Other(5)` (EIO), the descriptor closed all the same: `__close`'s errno ([[MYLA-378]]) |
| `f.descriptor() -> int32` | Its handle, which the descriptor primitives take for the descriptor it holds (`Pollable`; -1 for a `File` built by hand) |

A file a function opens is closed by that function: Myla has no destructors, so nothing closes it when it goes out of scope, and an open file stays open until `close` or the end of the program. `defer` right after the open is the idiom:

```myla fragment
var f = fs.open(path)?
defer { let closed = f.close() }
```

`Read` and `Write` deal in bytes (D177): text goes through `std.io`'s adapters, `buffered(f)` for lines and `buffered_writer(f)` with its `write_str`, or `std.bytes`'s `from_str` and `to_str` for a few bytes.

A `File` is a value holding a handle into the runtime's table (D181), and a copy of it holds the same handle: the same descriptor, with the same cursor, as the platform keeps it. So a reader can take a copy while the function keeps the file to close: `var r = buffered(f)` reads through `f`'s descriptor. `close` closes the descriptor and the handle for every copy: each later operation through any of them is `Other(9)` (EBADF), also after a file opened later got the descriptor's number from the platform (before D181 the copy then read and wrote that file), and so is one through a `File` built by hand. A failure is always an `IoError`, never a crash. A write to a file opened only to read is `Other(9)` too.

```myla
import std.fs as fs
from std.fs import IoError
from std.io import SeekFrom, buffered
import std.bytes as bytes

// A file written, appended to, read back by lines, and its size.
fun notes() -> Result<(), IoError> {
    let dir = fs.make_temp_dir()?
    defer { let gone = fs.remove_dir_all(dir) }
    let path = dir + "/notes.txt"
    var f = fs.create(path)?
    f.write(bytes.from_str("one\ntwo\n"))?
    f.close()?
    var log = fs.open_append(path)?
    log.write(bytes.from_str("three\n"))?
    log.close()?
    var file = fs.open(path)?
    defer { let closed = file.close() }
    var lines = buffered(file)
    while let Some(line) = lines.read_line()? {
        print(line)
    }
    file.seek(SeekFrom.Start(4))?
    print(bytes.to_str(file.read(3)?))
    let m = fs.metadata(path)?
    print(f"{m.size} bytes, a file: {m.is_file()}")
    return Ok(())
}

fun main() {
    match notes() {
        Ok(()) => {},
        Err(e) => { print("failed") },
    }
}
// output:
// one
// two
// three
// two
// 14 bytes, a file: true
```

Copying a stream of any size is a loop over a buffer: `copy` from `std.io` reads 64 KiB at a time, and a loop of `read(1 << 20)` and `write` with 1 MiB copies 4 GB from `/dev/zero` to `/dev/null` in the memory of a program that copies 1 MiB (below).

## Metadata

| Item | Result |
| --- | --- |
| `metadata(path: str) -> Result<Metadata, IoError>` | What the path names, symbolic links followed; a missing path, or a dangling link, is `NotFound` |
| `symlink_metadata(path: str) -> Result<Metadata, IoError>` | The path itself: a symbolic link isn't followed, its kind is `Symlink` and its size the length of the path it holds ([[MYLA-363]]) |
| `struct Metadata { size: int64, kind: FileKind, permissions: int32, modified_ns: int64 }` | The size in bytes, the kind, the permission bits (POSIX's `0o7777` on every target: a platform without them gives what its system has as such bits, D218), the last modification in nanoseconds since 1970 (`std.time.from_unix_ns(m.modified_ns)` is its `DateTime`) |
| `m.is_file() -> bool`, `m.is_dir() -> bool`, `m.is_symlink() -> bool` | Whether it is a regular file, a directory, a symbolic link |
| `enum FileKind { File, Dir, CharDevice, BlockDevice, Fifo, Socket, Symlink, Other }` | The kind, which the platform gives (its `KIND_FILE`, …; no type bits cross, D209); `Symlink` only from `symlink_metadata` |

Neither opens anything: they stat the path (`__path_stat`, [[MYLA-378]]), so a file the program may not read has its metadata too, and a device, a FIFO or a socket its own size and time (until November 2026 `metadata` opened files and directories to read them, and gave anything else size and time 0). On wasm32 there are no permissions: they are made up from the kind (0o644 for a file, 0o755 for a directory, 0o777 for a link, [[Language/Targets]]), and a device's or a FIFO's kind is `Other`. On Windows the permissions come from the read-only attribute (0o444 or 0o666, a directory 0o555 or 0o777, a link 0o777, D218), a directory's size is 0, and a pipe's or the console's kind is `Fifo` or `CharDevice` (below).

## Temporary files and directories

| Function | Result |
| --- | --- |
| `temp_root() -> str` | The directory for temporary files: `$TMPDIR` when it is set and not empty, else `/tmp`, without a trailing `/`; on Windows the first of `%TMPDIR%`, `%TEMP%` and `%TMP%` set, else `.`, without a trailing `/` or `\` |
| `make_temp_dir() -> Result<str, IoError>` | A new, empty directory in `temp_root()`, named `myla-` and 16 random hexadecimal digits, mode 0700: its path |
| `make_temp_dir_in(dir: str, prefix: str) -> Result<str, IoError>` | The same in `dir`, named `prefix` and the digits |
| `make_temp_file() -> Result<(str, File), IoError>` | A new, empty file in `temp_root()`, named `myla-` and 16 random hexadecimal digits, mode 0600, open for reading and writing: its path and the file |
| `make_temp_file_in(dir: str, prefix: str) -> Result<(str, File), IoError>` | The same in `dir` |

The digits come from the system's entropy (`__random_bytes`), and the name is made in one step that fails when it is taken (mkdir, or open with create and exclusive), so no other program can slip in a file or a link of its own; a taken name is tried again with new digits, up to 100 times, then it is `AlreadyExists`. Nothing removes them: the caller does, with `remove_dir_all` or `remove_file`, best in a `defer`. In a test, `std.test`'s `temp_dir()` and `temp_file()` make them in the case's scratch directory, which the runner removes ([[Language/Standard-library/Test]]).

## On Windows

On x86-64 Windows ([[MYLA-704]]) std.fs works over kernel32 through std.platform, as on the other targets: a path crosses as UTF-16 (`CreateFile2`, `GetFileInformationByHandle`, `GetFileInformationByHandleEx`'s directory records, `CreateDirectoryW`, `DeleteFileW`, `RemoveDirectoryW`, `MoveFileExW`, `GetCurrentDirectoryW`), its names UTF-8 in the program (D215), and a path's `\` separates as its `/` does, here as in std.path ([[Language/Standard-library/Path#on-windows]]). What a program sees is Linux's where Windows reports it otherwise:

- A file is opened sharing reading, writing and removing with every other handle, so another program's open file doesn't stop a write, a rename or a removal (one removed while open goes once the last handle closes).
- `read_to_string` of a directory, and `remove_file` of one, are `IsADirectory` (Windows: access denied); a path through a file (`make_dir("f.txt/x")`) is `NotADirectory` (Windows: a path not found); a name longer than 255 units is `Other` of the system's code for it (`Other(36)`, ENAMETOOLONG, on Linux; `Other(206)`, `ERROR_FILENAME_EXCED_RANGE`, on Windows); reading a `File` open only for writing, or the other way round, `Other(9)` (std's number of a handle that isn't open, Linux's EBADF, on every target). Windows' other codes are their causes, or `Other` of Windows' own code (D219, [[MYLA-716]]: a full disk `Other(112)`).
- `remove_file` of a symbolic link to a directory removes the link (`RemoveDirectoryW`); a read-only file isn't removed (`PermissionDenied`, as Windows has it, where Linux asks the directory); `rename` replaces a file there (`MOVEFILE_REPLACE_EXISTING`), not a directory.
- `current_dir()` is Windows' own path (`C:\Users\me`; under Wine the Unix root is `Z:\`); `make_dir_all` starts after a UNC path's server and share.
- `mode` (of `make_dir` and `OpenOptions.mode`) isn't used: Windows has no permission bits but the read-only attribute, and a new file isn't read-only (D218).
- A `File` opened to append writes at the end whatever its cursor (`FILE_APPEND_DATA` without `FILE_WRITE_DATA`). Seeking a pipe or the console is ESPIPE's `Other(29)`.
- The temporary files and directories go under `%TMPDIR%`, `%TEMP%` or `%TMP%`, else the working directory (D227), their names joined with `\` and made of random bytes from `BCryptGenRandom` ([[MYLA-722]]).

A symbolic link is a reparse point (a symbolic link's or a junction's tag) and `Symlink` as on Linux; Wine shows a Unix link as what it names, so the suites check links on Windows itself ([[MYLA-708]]). `read_link` reads the reparse point's data (`FSCTL_GET_REPARSE_POINT`): a symbolic link's or a junction's print name (`C:\www\app.css`, `..\app.css`), else its substitute name without `\??\`. `canonical` gives Windows' own path, as `current_dir` does (`C:\www\app.css`, `\\server\share\x`; `\x` is on the working directory's drive), each name spelled as written: it follows links itself, so a link that names a directory in another case leads to another spelling of the same directory.

## Measurements

Natively on x86-64, measured on the development container (4 cores of a Xeon at 2.1 GHz, shared with other work: a load of 3.5 to 5), 2026-11-11 at `bccc624`, the best of 16 runs in two sets (of 14 for the 1 MiB, of 5 for the 1 GiB), with a loop of `read(1 << 20)` and `write` through two `File`s:

| What | Time | Largest resident set |
| --- | ---: | ---: |
| 4 GiB (4,096 reads of 1 MiB) from `/dev/zero` to `/dev/null` | 82 ms | 11.4 MB |
| 1 GiB from a pipe to `/dev/null` | 29 ms | 11.4 MB |
| 1 MiB from a file to `/dev/null` | 2.4 ms | 11.4 MB |
| A 256 MiB file of random bytes to a new file (in the page cache) | 191 ms, 1.4 GB/s | 11.4 MB |

The memory doesn't grow with the size. A `File` reads into a `[uint8]` and writes from one itself (`__read_bytes`, `__write_bytes`, D177): converting the bytes from and to a `str` instead made the 4 GiB take 467 to 510 ms ([[MYLA-399]], 2026-11-09). `std.io`'s `copy` and the size of its pieces are measured on its page ([[Language/Standard-library/Io#speed]]).

## Directory primitives

The directory functions rest on seven primitives (D64's pattern: a small system call per implementation, the rest shared Myla code; [[MYLA-88]], [[MYLA-98]], [[MYLA-96]]):

| Primitive | Does | Result |
| --- | --- | --- |
| `__list_dir(path: str) -> str` | open(2) with `O_DIRECTORY`, the platform's `dir_read` until the end (getdents64(2)), close(2) | Every name the directory lists, each followed by a NUL byte, in the file system's order (`.` and `..` may be among them); `""` on an error |
| `__mkdir(path: str, mode: int32)` | mkdir(2) | Nothing |
| `__stat(path: str) -> int32` | stat(2) | The kind of what the path names: `std.platform`'s 1 a file, 2 a directory, 3 a link (never, as links are followed), 4 a character device, 5 a block device, 6 a FIFO, 7 a socket, 8 anything else; -1 on an error |
| `__getcwd() -> str` | getcwd(2) into a 4 KB buffer | The working directory, or `""` on an error (`NotFound` for a removed directory, ERANGE's `Other(34)` for a path longer than the buffer) |
| `__unlink(path: str)` | unlink(2) | Nothing (a directory is `IsADirectory`, which `remove_dir_all` uses to tell one without following links) |
| `__rmdir(path: str)` | rmdir(2) | Nothing |
| `__rename(from: str, to: str)` | rename(2) | Nothing |

The system calls named are x86-64 Linux's; aarch64 uses the generic `*at` forms (`openat`, `mkdirat`, `unlinkat`, `renameat2`), wasm32 WASI's (`path_open`, `fd_readdir`, …), translated into the same results. Each sets the cause code that `__io_errno()` reads (0 on success; std.ioerror's, D209), which `from_cause` reads: the platform module maps its system's codes onto them, and one with no cause is `Other` of the system's own code. wasm32 gives an `Other` the number Linux has for it (all 76 errnos of WASI preview 1: an ELOOP is `Other(40)` and an ENAMETOOLONG `Other(36)` there as here; one WASI doesn't define is 4096 plus its number, so it stays apart; until [[MYLA-426]] every one the table didn't know was EIO). The directory's entries come from the platform as names and kinds (`dir_entry_name`, `dir_entry_name_len`, `dir_entry_kind` over records of its own: getdents64's on Linux, WASI's own on wasm32), not as records std.rt parses. A name can't hold a NUL byte, so NUL separates them. `list_dir` drops `.` and `..` and sorts the names by their bytes, so every file system gives the same list (and the Python interpreter, with `os.listdir`, gave it too).

## Descriptor and entropy primitives

Files opened and read or written a piece at a time, at a cursor, and the system's entropy rest on these ([[MYLA-336]], D64's pattern again; the API over them is [[MYLA-339]]'s `File` and [[MYLA-337]]'s `std.random`). A descriptor is an `int`: a descriptor's own number below 2^23 (the standard streams', `io.fd_stream`'s), or a handle that holds one (D181: what `__open` and `__spawn_piped` give, a table index with a generation, which fails with `Other(9)` (BAD_HANDLE) once closed, through every copy); `__read(fd, n)` (one read of up to `n` bytes at the cursor, `""` at the end), `__write(fd, s)` (every byte of `s` at the cursor, again after a short write) and `__close(fd)` are the ones `std.io` and `std.process` already use.

| Primitive | Does | Result |
| --- | --- | --- |
| `__open(path: str, flags: int, mode: int) -> int` | open(2) with `O_CLOEXEC`; `flags` are Myla's own bits, the same on every target: 1 read, 2 write (both: read and write), 4 create, 8 truncate, 16 append (each write at the end, wherever the cursor is), 32 exclusive (with create: `AlreadyExists` when the file is there) | A handle for the descriptor, or -1. Without 1 or 2, with another bit, or a NUL in the path: `InvalidInput`. `mode` is the permissions of a file it creates, less the umask |
| `__seek(fd: int, offset: int64, whence: int) -> int64` | lseek(2): `offset` from the start (`whence` 0), the cursor (1) or the end (2) | The new offset from the start, or -1 (`InvalidInput` for another whence, a place before the start or one past the largest the file system allows, an `int64` overflowed included; ESPIPE's `Other(29)` for a pipe) |
| `__fstat(fd: int) -> [int64]` | fstat(2) | `[size, kind, permissions, mtime]`: the size in bytes, the kind as `__stat` gives it, the permission bits (`0o7777`), the modification time in nanoseconds since 1970; `[]` on an error |
| `__path_stat(path: str, follow: bool) -> [int64]` | `newfstatat`, with `AT_SYMLINK_NOFOLLOW` unless `follow` ([[MYLA-378]], [[MYLA-363]], [[MYLA-758]]: x86-64 called stat(2) and lstat(2)) | `[size, kind, permissions, mtime, dev, ino]`: `__fstat`'s four, then the device and the file's number on it (together they tell one file from another: `glob.walk_with` uses them to find a loop); a link itself is the kind 3. `[]` on an error (`NotFound` for a dangling link followed, `InvalidInput` for a NUL in the path) |
| `__random_bytes(n: int) -> [uint8]` | getrandom(2) until `n` bytes are there (a call gives at most 32 MB, and a signal may cut one of 256 bytes or more short) | `n` bytes; `[]` on an error (`InvalidInput` for a negative `n`) |

aarch64 opens with `openat` and stats with `newfstatat` (`AT_SYMLINK_NOFOLLOW` for a link itself); wasm32 uses `path_open` (the flags as its open flags, rights and `FDFLAGS_APPEND`), `fd_seek` (an offset the host gives past `int64`'s range is `InvalidInput`, as Linux's lseek gives past its largest; Node's shim, `tools/wasm/`, reckons the cursor exactly and refuses one past 2^53 - 1 or below 0 with EINVAL, the cursor unmoved, [[MYLA-426]]), `fd_filestat_get`, `path_filestat_get` (with `LOOKUPFLAGS_SYMLINK_FOLLOW` or without), `fd_close` and `random_get`. WASI has no permissions: `mode` is not used there, and the permissions `__fstat` and `__path_stat` give are made up from the file's kind (0o644 for a file, 0o755 for a directory, 0o777 for a link, 0o644 for anything else). Each sets `__io_errno()` as the directory primitives do, `__close` too since [[MYLA-378]] (`Other(9)` for a descriptor that isn't open, a negative one included; EIO's `Other(5)`; an interrupted close counts as closed, as Linux has closed it then); the interpreter calls the same primitives of its own.
