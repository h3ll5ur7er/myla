---
id: MYLA-326
title: "std.path and std.glob: paths, directory walks, glob patterns"
type: feature
status: done
priority: medium
labels: [stdlib, fs, wave-2]
---
Wave 2 of [[Project/Standard-library-roadmap]], roadmap #43, #44. Paths as strings, POSIX separators on every target.

- **Owns:** `lib/std/path.my`, `lib/std/glob.my`, `docs/Language/Standard-library/Path.md`, `docs/Language/Standard-library/Glob.md`
- **Needs:** [[MYLA-321]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [x] `std.path`: `join`, `parent`, `file_name`, `stem`, `extension`, `normalize` (`.` and `..` without the file system), `is_absolute`, `relative(from, to)`
- [x] `std.glob`: `matches(pattern, path)` for `*`, `?`, `**`, `[...]`, `[!...]`; `walk(dir)` (every path below a directory, sorted, links not followed) and `glob(pattern)`
- [x] The walk tested on every target (wasm32 included) with `test.temp_dir()`
- [x] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [x] Its page below [[Language/Standard-library]], with a doc block that runs

## Evidence

Built from master after wave 1 (087e4fe).

- **`std.path`** ([[lib/std/path.my]], [[Language/Standard-library/Path]]): `join`, `join_all`, `parent`, `file_name`, `stem`, `extension`, `with_extension`, `normalize`, `is_absolute`, `components`, `relative`. The edge cases were checked against Python's `posixpath` and `pathlib` in a scratch script (`""`, `"/"`, `"a/"`, `"//a"`, `"a/./b/../c"`, `.bashrc`, `...`, `foo.`, `a/.`, `/..`, `a/../..`). `normalize` agrees with `posixpath.normpath` but on `//a`, which is `/a` here (any run of leading slashes is the root, as on Linux and in Rust). `parent` and `file_name` follow Rust's `Path` (None for the root, `""` and `.`; trailing slashes and a trailing `.` don't count). `relative` gives `Option<str>`, not `str`: None where only the file system could answer (a relative `to` from an absolute `from_dir`, or `..` in `from_dir` above where `to` starts).
- **`std.glob`** ([[lib/std/glob.my]], [[Language/Standard-library/Glob]]): `matches`, `compile` and `Pattern.matches`, `walk`, `glob`, `glob_in`. `?` and sets match a UTF-8 character. `glob_in(dir, p)` gives what `walk(dir)` filtered by `matches(p, …)` gives (a test checks it on eight patterns), reading only the directories the pattern reaches.
- **Links**: `std.fs` has no `lstat` and `list_dir` drops getdents' `d_type`, so `walk` can't tell a link from a directory: it follows what `is_dir` follows. A loop `d/up -> ..` is gone round 40 times (Linux's limit); two such links would give 2⁴⁰ paths. Not following links needs a primitive (`__lstat`, or `d_type` from `__list_dir`): platform track.
- **Tests**: `myla test lib/std/path.my --stdlib lib` 92/92, `lib/std/glob.my` 51/51; the same with `--native`, `--target aarch64-linux` (qemu) and `--target wasm32-wasi` (Node). The walk and glob test functions make a tree under `/tmp` with `std.fs` and remove it in a `defer` (a `lib/std` module can't import `std.test`, so not `test.temp_dir()`). `python3 -m unittest tests.burn.test_std_modules tests.burn.test_doc_blocks`: 6 tests OK after a bootstrap.
- **wasm32 bug found and fixed** ([[lib/std/platform_wasm.my]], a commit of its own): `dir_read` keeps each directory descriptor's readdir cookie in slot `fd & 63` and never reset it when a directory was opened, so after 64 descriptors (Node's shim never reuses a number) `fs.list_dir` started at a stale cookie and gave a short or empty list. The glob test failed on wasm32 (49/50) before the fix, passes after it; `test-target.py wasm32-wasi test_fs` passes with it.
- **Measured** natively, best of 5: `matches("a*a*a*a*a*b", 10,000 a's)` 36 µs; `walk` over 100 directories of 100 files (10,100 paths) 7 ms; `glob_in(dir, "**/*7.txt")` over it (1,000 matches) 11 ms.

## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]], with a follow-up in [[MYLA-426]]: `glob_in` differs from `walk` + `matches` for a dangling link named literally and for a file before `/**`.

The follow-up is done in [[MYLA-426]] (in review, 2026-11-11): a literal component is found as `walk` lists it (a dangling link too), and a file before `/**` matches, as `walk` and `matches` say.
