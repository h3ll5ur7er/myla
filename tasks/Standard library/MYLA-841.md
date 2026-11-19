---
id: MYLA-841
title: "std.fs: where a symbolic link leads, so static_files can follow one that stays under its root"
type: feature
status: review
priority: low
labels: [stdlib, fs, http]
---
Found by [[MYLA-795]]. D260 says `static_files` serves "no symlinks out of the root". std.fs can't say where a link leads: there is no `read_link` and no canonical path (`realpath`), and no primitive to build either (`__path_stat` gives a link's size, kind, permissions, time, device and number, not its target). So [[MYLA-795]] refuses every symbolic link below the root, one that stays inside it too (on Windows every reparse point `symlink_metadata` gives as `Symlink`: a symbolic link or a junction).

Reproduction: a served directory `www/` with `app.css` and `www/inlink.css -> app.css`; `GET /assets/inlink.css` is 404 (`tests/burn/test_router.py`, `POLICY`, the line `/assets/inlink.css 404 not found`).

- [x] A primitive that reads a link (`readlink` on Linux and WASI's `path_readlink`, `DeviceIoControl(FSCTL_GET_REPARSE_POINT)` or `GetFinalPathNameByHandleW` on Windows) and its interpreter twin, staged in the seeds (D207)
- [x] `fs.read_link(path)` and `fs.canonical(path)` (an absolute path without links, `.` or `..`), with `#test` cases and `tests/burn/test_fs.py` cases on every target (Windows: its cases under Wine, links only on Windows itself, below)
- [x] `static_files` follows a link whose canonical path stays under the canonical root, and `POLICY`'s `inlink.css` line becomes 200 (D260's letter); a decision for the owner if links out of the root should stay 404 or become an option (proposed below: they stay 404)

## What changed

- **`__read_link(path)`** (staged in `c984abf`): what a link holds, as written in it, not followed; "" with INVALID_INPUT for a path that is no link. [[lib/std/rt.my]] `read_link` (a room of 1 KiB, doubled up to 64 KiB) over a new `read_link(path, buf, n)` of each platform module: `readlinkat` on Linux (`SYS_READLINKAT` in both [[lib/std/linux_calls.my]] copies), `path_readlink` on WASI (a new import, 21; `memory.grow` moved to 22; the shim's `path_readlink` and `readlink` of its file systems, [[tools/wasm/wasi.mjs]], `node_fs.mjs`, `mem_fs.mjs`), on Windows the reparse point opened itself and its data read with `DeviceIoControl(FSCTL_GET_REPARSE_POINT)` (`link_text`: a symbolic link's or a junction's print name, else the substitute name without `\??\`, `\??\UNC\` as `\\`; a WSL link's text). The interpreter calls the host's ([[selfhost/interp.my]] `B_READ_LINK`); the checker's `is_platform_primitive` and `infer_platform_primitive` know it.
- **std.fs** ([[lib/std/fs.my]]): `read_link(path)` and `canonical(path)`. `canonical` resolves in Myla, the same on every target, as realpath(3) does: a relative path from `current_dir`, each part looked at with `symlink_metadata`, a link read and its parts put before the rest (an absolute one starting again from its root), `..` taking the last part off, more than 40 links `Other(40)`, a missing part `NotFound`, a file before the end `NotADirectory`. On Windows the roots are a drive's or a share's (`split_root`: `C:\`, `\\srv\share\`, the verbatim forms too) and the separator `\`, the path as `current_dir` gives it.
- **`static_files`** ([[lib/std/http.my]] `file_response`, `served_under`): a link below the root is followed when `canonical` of it is under `canonical` of the root and `served_segments` takes its parts below the root (so a link to `.env` is refused as `.env` is, and on Windows to a device's name); the walk goes on from where it led, which is the path the server opens (MYLA-842 opens it without following a link at the end).

## Proposals

- **One primitive, `__read_link`, and the canonical path in Myla** (built). Alternatives: *(a)* a canonical-path primitive: Linux has no `realpath` call (it would be `open(O_PATH)` and `/proc/self/fd`, which a sandbox may lack), WASI none at all, so it would be Myla over `readlink` there anyway; Windows' `GetFinalPathNameByHandleW` would give the volume's own spelling (case and 8.3 names made long), which `canonical` doesn't: a link that names the served directory in another case is refused on Windows (a refusal, never a file out of the root). *(b)* `GetFinalPathNameByHandleW` for Windows' `read_link`: it gives where a whole path ends, not what one link holds.
- **Links out of the root stay 404, with no option** (built). An option to serve them would let a link someone made under the root publish anything the server can read; nginx's `disable_symlinks if_not_owner` is the nearest thing and needs owners Myla doesn't read.
- Proposed row, changing D284: *"`static_files` follows a symbolic link below its root when where it leads (`fs.canonical`) is under where the root leads and the path from there passes the root's rules (no dot file, no device's name); a link out of the root stays 404, with no option ([[MYLA-841]], D260; changes D284, which refused every link)."*

## Evidence

- **Before** (BASE `569f9f0`): `POLICY` had `/assets/inlink.css 404 not found`; `__read_link` is `unknown function` to the checker.
- **After**: `test_router.StaticFiles` passes with `/assets/inlink.css 200 body {}` and six new lines (a link to a directory beside it, one that leaves and comes back, to `.env` 404 and 200 under `dot_files`, to a FIFO 404, to the root itself), interpreted and native. `test_platform_primitives.Paths.test_read_link` (relative, dangling, `../`, a 4,001-byte target read in three rooms; a file, nothing and a NUL with their causes). `test_fs.DirectoryParity.test_where_links_lead` (23 lines: `read_link` and `canonical` through chains, absolute links, `..` after links, a loop, a dangling link). std.fs's `canonical_paths` and the helpers' cases: 93/93 interpreted, `--native`, aarch64 (qemu), wasm32 (Node) and x86-64 Windows (Wine 9.0).
- **Targets**: `scripts/test-target.py` aarch64-linux and wasm32-wasi pass test_fs, test_router and test_platform_primitives; x86_64-windows passes them under Wine with the link tests excused (`_WINE_LINKS`: Wine shows a Unix link as what it names, and its `mklink` made no link here).
- **Only Windows itself shows** `read_link` of a symbolic link and a junction, `canonical` through them and `static_files` following them: the Windows runner's new case `files/links` ([[scripts/windows-runner.py]], `test_windows.WINDOWS_LINKS`: links made by `mklink` and `mklink /J`) runs on CI's `windows-latest` job and is skipped under Wine. It needs `mklink`'s privilege for a symbolic link, which the runner's administrator has.
