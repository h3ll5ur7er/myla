---
id: MYLA-729
title: "myla.exe's scratch directories on Windows: TEMP, not /tmp"
type: bug
status: todo
priority: low
labels: [platforms, windows, testing]
---
Found by [[MYLA-728]], which moved a Windows test harness's case directories under `%TEMP%` (std.fs's `temp_root`). The toolchain's own scratch directories still take `TMPDIR`, else `/tmp`, joined with `/`: `myla test --native`'s harness build in [[selfhost/driver.my]] (`format("{}/myla-test-{}", base, now_ns())`), a project's in [[selfhost/project_cmd.my]], and the interpreter's case root in [[selfhost/interp.my]] (`__getenv("TMPDIR")`, `/tmp`). On Linux nothing changes; `myla.exe` running on Windows itself ([[MYLA-708]]'s runner) would make `\tmp\myla-test-…` on the current drive instead of a directory under `%TEMP%`.

- [ ] The three take std.fs's `temp_root()` (the interpreter its own equivalent) and join with the target's separator, as std.test's `run_in_children` does since [[MYLA-728]]
- [ ] Checked by `myla.exe test` on the Windows runner, outside Wine's `Z:`
