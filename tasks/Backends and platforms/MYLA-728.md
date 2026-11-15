---
id: MYLA-728
title: "std.test's case directories on Windows: TEMP, not /tmp"
type: bug
status: todo
priority: low
labels: [platforms, windows, testing]
---
Found by [[MYLA-705]], which runs a native test harness's cases as children on Windows (D217's `spawns`). `run_in_children` ([[lib/std/test.my]]) puts each case's scratch directory (MYLA_TEST_DIR) under `TMPDIR`, else `/tmp`. On Windows `TMPDIR` is rarely set, and `/tmp` is a directory of the current drive that isn't there. Under Wine it is `Z:\tmp`, which is Linux's, so it works there. Files come with [[MYLA-704]]; once they do, a case that uses `test.temp_dir()` on Windows needs a directory that exists.

- [ ] On Windows the root is `TEMP` (else `TMP`, else the system's temporary directory), joined with `\`
- [ ] A test of a case's `temp_dir()` under Wine and, on a Windows runner ([[MYLA-708]]), outside Wine's `Z:`
