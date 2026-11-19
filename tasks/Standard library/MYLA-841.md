---
id: MYLA-841
title: "std.fs: where a symbolic link leads, so static_files can follow one that stays under its root"
type: feature
status: in-progress
priority: low
labels: [stdlib, fs, http]
---
Found by [[MYLA-795]]. D260 says `static_files` serves "no symlinks out of the root". std.fs can't say where a link leads: there is no `read_link` and no canonical path (`realpath`), and no primitive to build either (`__path_stat` gives a link's size, kind, permissions, time, device and number, not its target). So [[MYLA-795]] refuses every symbolic link below the root, one that stays inside it too (on Windows every reparse point `symlink_metadata` gives as `Symlink`: a symbolic link or a junction).

Reproduction: a served directory `www/` with `app.css` and `www/inlink.css -> app.css`; `GET /assets/inlink.css` is 404 (`tests/burn/test_router.py`, `POLICY`, the line `/assets/inlink.css 404 not found`).

- [ ] A primitive that reads a link (`readlink` on Linux and WASI's `path_readlink`, `DeviceIoControl(FSCTL_GET_REPARSE_POINT)` or `GetFinalPathNameByHandleW` on Windows) and its interpreter twin, staged in the seeds (D207)
- [ ] `fs.read_link(path)` and `fs.canonical(path)` (an absolute path without links, `.` or `..`), with `#test` cases and `tests/burn/test_fs.py` cases on every target
- [ ] `static_files` follows a link whose canonical path stays under the canonical root, and `POLICY`'s `inlink.css` line becomes 200 (D260's letter); a decision for the owner if links out of the root should stay 404 or become an option
