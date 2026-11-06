---
id: MYLA-286
title: A NUL byte in a path is silently truncated
type: bug
status: todo
priority: medium
labels: [stdlib, fs, safety]
---
Found by the review of 6 November 2026 ([[Project/Review-2026-11]]). `std.fs` hands a path's bytes to the platform layer, which hands a C string to the kernel: `write_to_file("fsp/q\u{0}zzz", "x")` creates `fsp/q`, and `read_to_string("fsp/q\u{0}other")` reads it (both runners). A path built from user input can address another file. Rust answers `InvalidInput`.

- [ ] The path entry points of `std.rt` (open, stat, unlink, rmdir, rename, mkdir, readdir) reject a path with a NUL byte: an `IoError` cause (`InvalidInput`, to add to D129's list) in both runners and on every target
- [ ] A `test_fs` case
