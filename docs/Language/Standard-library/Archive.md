# std.archive

tar archives, read and written, and zip archives, read ([[MYLA-352]]). The compression around them is [[Language/Standard-library/Compress]].

```myla
import std.archive as archive
import std.compress as compress
import std.encoding as encoding
import std.bytes as bytes
import std.io as io

fun main() {
    var notes = archive.file("notes/today.txt", bytes.from_str("buy milk\n"))
    notes.mtime = 1700000000
    let entries = [archive.dir("notes"), notes, archive.symlink("latest", "notes/today.txt")]
    let tar = archive.tar_write(entries).unwrap_or([])
    print(f"{tar.len()} bytes of tar")

    // gzipped, then read back as a stream, as a .tar.gz is read
    var r = archive.tar_reader(compress.gzip_reader(io.from_bytes(compress.gzip(tar))))
    while let Some(got) = r.next() {
        match got {
            Ok(e) => print(f"{e.name}: {e.data.len()} bytes, mode {e.mode:o}")
            Err(e) => print(f"error: {e}")
        }
    }

    // a zip archive Python's zipfile wrote, with a.txt stored in it
    let z = encoding.hex_decode("504b03041400000000000000215286a61036050000000500000005000000612e74787468656c6c6f504b010214031400000000000000215286a610360500000005000000050000000000000000000000a48100000000612e747874504b0506000000000100010033000000280000000000").unwrap_or([])
    match archive.zip_read(z) {
        Ok(files) => {
            for f in files { print(f"{f.name}: {bytes.to_str(f.data)}") }
        }
        Err(e) => print(f"error: {e}")
    }

    // where an entry may be extracted
    for name in ["notes/today.txt", "../../etc/passwd", "C:\\boot.ini"] {
        let p = archive.safe_path("out", name)
        match p {
            Ok(path) => print(f"{name} -> {path}")
            Err(e) => print(f"{name}: {e}")
        }
    }
}
// output:
// 3072 bytes of tar
// notes: 0 bytes, mode 755
// notes/today.txt: 9 bytes, mode 644
// latest: 0 bytes, mode 777
// a.txt: hello
// notes/today.txt -> out/notes/today.txt
// ../../etc/passwd: entry name leaves the directory
// C:\boot.ini: entry name leaves the directory
```

## Entries

An `Entry` is one member of an archive, tar's or zip's. Its fields are public: make one with `file`, `dir` or `symlink`, then set the others.

| Field | What it is |
| --- | --- |
| `name: str` | The path inside the archive, its parts split by `/` whatever the system, without a `/` at its end for a directory |
| `kind: EntryKind` | `File`, `Dir`, `Symlink`, `Hardlink`, or `Other(flag)`: another tar type by its typeflag, a device (`3`, `4`), a FIFO (`6`), GNU's sparse files (`S`) |
| `mode: int32` | The permission bits, `0o644` |
| `mtime: int64` | The modification time, seconds since 1970 (UTC) |
| `uid`, `gid: int64`; `uname`, `gname: str` | The owner (tar; 0 and empty in zip). An `int64`, as a tar id may be 2^31 or more (`4294967294`, `nobody` on some systems; [[MYLA-423]]) |
| `link: str` | A link's target |
| `data: [uint8]` | A file's bytes (empty for the other kinds) |

| Function | Result |
| --- | --- |
| `file(name: str, data: [uint8]) -> Entry` | A file, mode `0o644`, time 0, owner 0 |
| `dir(name: str) -> Entry` | A directory, mode `0o755` |
| `symlink(name: str, target: str) -> Entry` | A symbolic link, mode `0o777` |

`Entry` and `EntryKind` are `Eq` (derived).

## tar

| Item | What it is |
| --- | --- |
| `tar_read(b: [uint8]) -> Result<[Entry], ArchiveError>` | Every entry of the archive `b` |
| `tar_reader<R: Read>(r: R) -> TarReader<R>` | The entries of the archive the stream `r` reads, one at a time: `Iterator<Result<Entry, ArchiveError>>`, an error once, then the end. A `.tar.gz` is `tar_reader(compress.gzip_reader(f))` |
| `tar_write(entries: [Entry]) -> Result<[uint8], ArchiveError>` | The archive of `entries`, in their order |
| `tar_writer<W: Write>(w: W) -> TarWriter<W>` | A writer of an archive to the stream `w`: `t.add(e) -> Result<(), ArchiveError>` writes an entry, `t.finish() -> Result<W, ArchiveError>` the end of the archive, and gives back `w`, flushed. A `.tar.gz` is `tar_writer(compress.gzip_writer(f, 9))`, then `finish` both |

Writing is POSIX's ustar, as `tar --format=pax` and Python's `tarfile` write it. A name longer than ustar's 100 bytes is split at a `/` into its prefix field (155 bytes) and its name; one that can't be split, a link longer than 100 bytes, an owner's name longer than 32 bytes, and a number its octal field can't hold (a time before 1970 or after 2242, an id of 2^21 or more) go in a pax extended header (typeflag `x`, named `././@PaxHeader`) before the entry, as `path`, `linkpath`, `uname`, `gname`, `mtime`, `uid`, `gid` and `size` records. A directory's name gets its `/`. The archive ends with two zero blocks; it isn't padded to tar's records of 10240 bytes, which no reader needs. A name that is empty or holds a NUL byte, or a link that holds one, is `BadName`.

Reading takes what GNU tar and Python write: ustar and its prefix, pax headers (`x`, and the global `g`, whose records hold for every entry after it), GNU's long names and links (`L`, `K`: `tar --format=gnu`, GNU tar's default) and its base-256 numbers, and the old v7 headers (a file whose name ends with `/` is a directory). A header's checksum is checked, unsigned or signed as old tars summed it, and its number fields (mode, owner, size, time) must be numbers, octal or base 256, in every header, a pax header's and a long name's too, as Python's `tarfile` and GNU tar have them. A pax `size` is the data's length; `mtime` keeps the whole seconds; `size`, `uid` and `gid` are integers. A number that doesn't fit an `int64`, in a header or a pax record (`mtime=99999999999999999999999999`), is `BadHeader`, as GNU tar refuses it (D184; Python's `tarfile` reads a pax time as a float, and a pax number that isn't one as 0). Only files and the types tar doesn't know have data, as in Python's `tarfile`. A pax header or a long name must have an entry after it. The archive ends at a zero block or at the end of the input after a whole entry, whose padding may be missing.

## zip

| Item | What it is |
| --- | --- |
| `zip_read(b: [uint8]) -> Result<[Entry], ArchiveError>` | Every entry of the archive `b` with its data; a symbolic link's target is its `link` |
| `zip_list(b: [uint8]) -> Result<[ZipFile], ArchiveError>` | The central directory: each entry's `name`, `kind`, `mode`, `mtime`, `method` (0 stored, 8 deflate), `flags`, `crc`, `size`, `csize` (compressed) and `offset` (of its local header), without reading its data |
| `zip_data(b: [uint8], f: ZipFile, max_output: int = 0x7FFFFFFF) -> Result<[uint8], ArchiveError>` | The data of one entry, decompressed, its length and CRC-32 checked. An entry whose `size` is more than `max_output` is `TooLarge`, before its data is read; a deflate entry is decompressed up to its `size` and no further (more data is `LengthMismatch`), so no entry takes more memory than its directory says. A `max_output` below 0 is a runtime error ([[MYLA-423]]) |

A zip archive is read from its end: the end of the central directory (after a comment of up to 65535 bytes), then the directory, then each entry's local header and data. Bytes before the archive, as a self-extracting program has, are allowed: the offsets move with them. A deflate entry must be one whole DEFLATE stream (Python's `zipfile` takes one that stops short of its end, if the CRC is right). An entry made on Unix has its mode and kind (a directory, a symbolic link) from the high bits of its external attributes; another one is a directory if its name ends with `/`. The time is an extended-timestamp field's (0x5455, which `zip` writes) if there is one, else the MS-DOS time, which is local time, taken as UTC. A name is its bytes, UTF-8 or not. ZIP64 archives, encrypted entries and methods other than stored and deflate are errors; writing zip isn't there yet. A number of the directory that points outside the archive, whatever its size, is an error (`BadHeader`, `Truncated`), never an overflow (D184).

## Extracting

Extracting is the caller's work, through std.path and std.fs, because only the caller knows where and how. Names come from the archive, so a name may try to leave the directory: `../../etc/passwd`, `/etc/passwd`, or on Windows `C:\boot.ini` and `..\x`.

| Function | Result |
| --- | --- |
| `is_safe_name(name: str) -> bool` | Whether `name` stays under a directory it is joined to: it isn't empty and holds no NUL byte, doesn't start at a root (`/`, `\`) or with a drive (`C:`), and no part of it is `..`; both `/` and `\` split it into parts, as Windows reads a path |
| `safe_path(dir: str, name: str) -> Result<str, ArchiveError>` | `path.join(dir, name)` if the name is safe, else `UnsafeName` |

A symbolic link can still point outside: check its `link` with `is_safe_name` too, or don't make links.

## Errors

`ArchiveError` is a bare enum (D168), with `message()`, `Format` and `Eq` (two errors are equal when their messages are).

| Variant | Meaning |
| --- | --- |
| `Truncated` | The archive ends inside a header or an entry's data |
| `BadHeader` | A tar header whose checksum is wrong or whose numbers aren't numbers, a pax record that isn't one, a number past `int64`; a zip record without its signature, or whose lengths point outside the archive |
| `BadName` | An entry to write whose name is empty or holds a NUL byte, or whose link holds one |
| `NotZip` | No end of a central directory |
| `Zip64` | A ZIP64 archive (more than 65535 entries, or past 4 GiB) |
| `Encrypted` | An encrypted zip entry |
| `Unsupported(method)` | A zip entry compressed by another method than stored and deflate |
| `ChecksumMismatch` | A zip entry's CRC-32 isn't its data's |
| `LengthMismatch` | A zip entry's data isn't as long as its directory says |
| `Compress(CompressError)` | A zip entry's DEFLATE data that doesn't decompress |
| `TooLarge` | `zip_data`: an entry longer than its `max_output` |
| `UnsafeName` | `safe_path`: a name that would leave the directory |
| `Io(IoError)` | The stream failed |

## Tests

The module's cases are tar fields and numbers (octal, base 256, pax records and their lengths, the split of a long name), safe and unsafe names, and zip archives written by Python's `zipfile`, whole, cut short and with a byte changed; and test functions: entries of every kind and field, names and a link too long for ustar among them, written and read back whole and from a stream that gives 1 to 700 bytes a read; the bytes of the headers; GNU's long names and a global pax header made by hand; a zip directory, a prefix before the archive, and an encrypted entry and an unknown method. [[MYLA-423]] added numbers at and past `int64`'s ends (base 256, pax records, the review's 26-digit `mtime`), owners of 2^31 and more in GNU's and pax's forms written and read back, headers whose numbers aren't numbers, a pax header with no entry after it, and `zip_data`'s `max_output` and directory numbers out of range. All 112 cases pass interpreted, natively, on aarch64 under qemu and on wasm32 under Node.

`tests/burn/test_archive.py` lists, natively, tar files that GNU tar 1.35 made in the gnu, posix, ustar and v7 formats and that Python's `tarfile` made in its GNU, PAX and USTAR formats, plain and gzipped (those also through `gzip_reader`), and zip files that `zipfile` made, stored and deflated at every level, and that `zip -0`, `-6` and `-9` made; the tree has names longer than 100 and 255 bytes, a non-ASCII name, files of 0, 512 and 513 bytes, an empty directory, and symbolic and hard links. Each listing must be Python's. It writes a tar file, plain and through a gzip writer at four levels, that `tarfile` must read as written and `tar -x` must extract; and changes a bit of 60 zip entries' data, each of which must fail where Python fails. A few run interpreted.

Its fuzz tests ([[MYLA-423]]) run a driver built plain and one built `--checked` on each input, which must give the same output, and a failure must be the driver's own error, not a runtime error (D184): 400 tar files with a field of a header changed (a number, digit by digit, in octal or in base 256; a name, a link, an owner, the type, the prefix, the magic), its checksum made again seven times in eight, or cut short; 250 PAX archives that `tarfile` wrote with records of odd values (numbers past `int64`'s ends, fractions, `1e5`, `+5`, `1_000`, an Arabic digit, empty), every third with a byte of its records changed; 150 zip files with a byte of their central directory changed; and the 60 zip entries above. A tar file std.archive reads, Python's `tarfile` must read with the same listing; std.archive may refuse one `tarfile` reads (a number past `int64`, a number in a looser form, a header after the first that `tarfile` takes for the end of the archive). Python's quirks are left out of the changes: `tarfile` joins a prefix whatever the magic says, takes `S` and `X` for its own formats, gives an extended header's records to the entry after a long name, and after an extended header takes a v7 file whose name ends in `/` for a file and cuts the `/`s off any path. Of 4000 changed headers, none disagreed.
