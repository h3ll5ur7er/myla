---
id: MYLA-326
title: "std.path and std.glob: paths, directory walks, glob patterns"
type: feature
status: backlog
priority: medium
labels: [stdlib, fs, wave-2]
---
Wave 2 of [[Project/Standard-library-roadmap]], roadmap #43, #44. Paths as strings, POSIX separators on every target.

- **Owns:** `lib/std/path.my`, `lib/std/glob.my`, `docs/Language/Standard-library/Path.md`, `docs/Language/Standard-library/Glob.md`
- **Needs:** [[MYLA-321]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] `std.path`: `join`, `parent`, `file_name`, `stem`, `extension`, `normalize` (`.` and `..` without the file system), `is_absolute`, `relative(from, to)`
- [ ] `std.glob`: `matches(pattern, path)` for `*`, `?`, `**`, `[...]`, `[!...]`; `walk(dir)` (every path below a directory, sorted, links not followed) and `glob(pattern)`
- [ ] The walk tested on every target (wasm32 included) with `test.temp_dir()`
- [ ] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [ ] Its page below [[Language/Standard-library]], with a doc block that runs
