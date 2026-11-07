---
id: MYLA-286
title: A NUL byte in a path is silently truncated
type: bug
status: review
priority: medium
labels: [stdlib, fs, safety]
---
Found by the review of 6 November 2026 ([[Project/Review-2026-11]]). `std.fs` hands a path's bytes to the platform layer, which hands a C string to the kernel: `write_to_file("fsp/q\u{0}zzz", "x")` creates `fsp/q`, and `read_to_string("fsp/q\u{0}other")` reads it (both runners). A path built from user input can address another file. Rust answers `InvalidInput`.

- [x] The path entry points of `std.rt` (open, stat, unlink, rmdir, rename, mkdir, readdir) reject a path with a NUL byte: an `IoError` cause (`InvalidInput`, to add to D129's list) in both runners and on every target
- [x] A `test_fs` case

## Done (2026-11-07)

- `std.rt`'s `stat`, `mkdir`, `unlink`, `rmdir`, `rename`, `read_file`, `write_file` and `list_dir` refuse a path with a NUL byte (`nul_in`) with EINVAL before any system call; `std.fs.from_errno` maps 22 to the new `IoError.InvalidInput` (and the project tool names it). Both runners and every target go through `std.rt`, so they agree.
- `test_fs.DirectoryParity.test_a_nul_byte_in_a_path`: every entry point gives `InvalidInput`, `q\u{0}zzz` creates no `q`, and the working directory holds only the `q` the program wrote itself, interpreted and natively. Adding the variant breaks an exhaustive `match` on `IoError`, as `BrokenPipe` did.
