---
id: MYLA-363
title: "std.fs can't tell a symbolic link from what it points to"
type: improvement
status: backlog
priority: low
labels: [fs, platforms, primitives]
---
Found by the `std.glob` lane ([[MYLA-326]]). `std.fs` has no `lstat`, and `__list_dir` drops the `d_type` that getdents gives. So `glob.walk` follows a link to a directory, as `is_dir` does. A loop `d/up -> ..` is walked 40 times, to Linux's limit; two such links would give about 2^40 paths.

- [ ] A primitive for a link's own kind (`__lstat`, or `d_type` passed out of `__list_dir`) on every target
- [ ] `fs.is_symlink(path)`, and `walk` that doesn't follow links (with an option to)

## Comments

- 2026-11-08: a path's `stat` is filed with the other wave 3 primitives, [[MYLA-378]].
