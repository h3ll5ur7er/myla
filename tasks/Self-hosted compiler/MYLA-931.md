---
id: MYLA-931
title: "The loader takes a Windows path for one part: relative imports and std files aren't found from a path with `\\` or a drive"
type: bug
status: done
priority: high
labels: [loader, windows]
---
Found by [[MYLA-926]] step 2's port of the burn suites (2026-11-24, group G4), reproduced under Wine with a Windows-built `myla.exe`: an entry named the way Windows names it (`Z:\…\app\main.my`) couldn't resolve its relative imports (`module error: cannot resolve import '.helper'`), and `myla test Z:\…\lib\std\option.my` failed with 18 duplicate-method errors (the file wasn't recognised as the std module the prelude had already loaded). The same commands with `/` passed.

`selfhost/loader.my` split, joined and compared paths with `/` alone and took a path as absolute only when it began with `/`, so `C:\w\main.my` was one relative part: its directory was `.`, and `same_file`, `in_stdlib` and `in_std_tree` joined it onto the working directory.

- [x] `slashed` (on Windows each `\` read as `/`), `has_drive`, `is_absolute` (`/`, a drive, a share); `normalize` slashes first, keeps a drive as its root (never popped by `..`, `C:/` for a bare drive) and a share's `//`
- [x] `same_file`, `in_stdlib`, `in_std_tree` and `std_tree_root` through `is_absolute` and the share's root
- [x] Evidence: under Wine, `myla run Z:\…\app\main.my` (a `.helper` import) prints `hi`, `myla test Z:\…\lib\std\option.my` 17/17, `myla check Z:\…\lib\std\fs.my` ok; on Linux `build/myla test selfhost/loader.my` 198/198, the bootstrap's fixed point, test_compiler_parity, test_error_corpus, test_modules, test_std_modules and test_lazy_std pass

The project tool's own paths are [[MYLA-930]].
