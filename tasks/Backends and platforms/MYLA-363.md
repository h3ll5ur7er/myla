---
id: MYLA-363
title: "std.fs can't tell a symbolic link from what it points to"
type: improvement
status: done
priority: low
labels: [fs, platforms, primitives]
---
Found by the `std.glob` lane ([[MYLA-326]]). `std.fs` has no `lstat`, and `__list_dir` drops the `d_type` that getdents gives. So `glob.walk` follows a link to a directory, as `is_dir` does. A loop `d/up -> ..` is walked 40 times, to Linux's limit; two such links would give about 2^40 paths.

- [x] A primitive for a link's own kind (`__lstat`, or `d_type` passed out of `__list_dir`) on every target
- [x] `fs.is_symlink(path)`, and `walk` that doesn't follow links (with an option to)

## What was built

- The primitive is [[MYLA-378]]'s `__path_stat(path, follow)` with `follow` false (lstat, `newfstatat` with `AT_SYMLINK_NOFOLLOW`, WASI's `path_filestat_get` without the follow flag), not `d_type` out of `__list_dir`: one stat per entry, as `is_dir` already made, keeps `__list_dir`'s result as it is, and gives the device and file number a walk that follows links needs to tell a loop.
- `fs.is_symlink(path)`, `fs.symlink_metadata(path)` (a link itself: kind `Symlink`, its size the length of the path it holds), `FileKind.Symlink`, `Metadata.is_symlink()`.
- `glob.walk(dir)` lists a link but doesn't go into it; `glob.walk_with(dir, follow_links)` follows links when asked, but not into a directory the walk is already in (by `__path_stat`'s device and file number), so a link back up is listed and not gone round. A `**` in a pattern doesn't go into a link to a directory either, as bash's globstar doesn't; a component that isn't `**` (`la/*`) follows one, as shells do.

## Proposal (open decision)

`walk_with(dir, follow_links: bool)` is the option: Myla has no default arguments, and a builder (`walk_options().follow_links(true).walk(dir)`) would be one struct for one switch. Following, a loop is skipped silently (GNU `find -L` warns, Rust's walkdir gives an error). I recommend both as built; an error for a loop could come with a `WalkError` if a caller needs to know.

## Evidence

- Before, with eaa905d's library, natively: a tree `t/a/x.txt` with one link `t/a/up -> ..` walks to `123 paths: a a/up a/up/a ... a/x.txt` (round the loop to ELOOP). After: `3 paths: a a/up a/x.txt`.
- `tests/burn/test_fs.py`'s `test_symbolic_links` (new): `is_symlink` of a link, a dangling link, a file, a directory; `symlink_metadata` of a link; `walk` (`a a/up a/x.txt dangling f.txt la lf secret`), `walk_with(t, true)` (`la` gone into, `a/up` and `la/up` listed but not gone round), `glob_in(t, "**")` and `glob_in(t, "la/*")`: the same output interpreted and natively, and under `scripts/test-target.py aarch64-linux` and `wasm32-wasi` (`tests.burn.test_fs` OK on both). Python makes the links, as std.fs has no `symlink` (not asked for here).
- `kind_of(0o120777)` is `Symlink` now (its `#test`), `Metadata.is_symlink`'s cases; `fs.my`'s `metadata_of_paths` checks `symlink_metadata` of a file and a directory is their `metadata`, and `is_symlink` of none. `build/myla test lib/std/fs.my --stdlib lib` 67/67 interpreted and `--native`; `lib/std/glob.my` 51/51.
- The walk over 100 directories of 100 files (10,100 paths) took 10 to 13 ms natively before and after, `glob_in(**/*7.txt)` 14 to 16 ms (one stat per path both times).
- The suites: see [[MYLA-369]]'s evidence.

## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]].
