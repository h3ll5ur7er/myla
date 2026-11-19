---
id: MYLA-817
title: "`myla run` releases the whole interpreter before it exits"
type: improvement
status: review
priority: low
labels: [interpreter, performance]
---
Found by [[MYLA-792]] while measuring the start-up. At the end of `myla run`, `cmd_interp` ([[selfhost/driver.my]]) returns its status and so releases the interpreter, the checker and the program it holds, value by value, just before the process exits: under callgrind, `myla run` of an empty program spends 2.6 M of its 29.3 M instructions in the release walk of `Interp` (`myla___walkd_interp$Interp`, 2,638,374 instructions; 2026-11-17 on `fe30af6` with [[MYLA-792]]'s lazy constants).

```myla fragment
fun main() {
}
```

`valgrind --tool=callgrind build/myla run empty.my`, then `callgrind_annotate --inclusive=yes` (with `build/myla build -g selfhost/main.my` for the names).

- [x] `myla run` ends with the program's status without releasing what the process gives back anyway (an `exit` where `cmd_interp` has its status, or a release the runtime skips at the end), in every caller of `cmd_interp` (the CLI, the playground's `play_main.my`, which may run more than one program in a process)
- [x] The instruction count of an empty program's `myla run`, before and after, pinned with date and hash (D197)

## Evidence

- [[selfhost/driver.my]] `cmd_interp` ends the process with the program's status (`exit(code)`) once it has it, so the interpreter, the checker and the program are left to the exit; a program that doesn't load still returns 1. Every caller ends with the status anyway: [[selfhost/main.my]] (`exit(cmd_interp(…))`, and `project_run` under `exit(…)`), and the playground's [[selfhost/play_main.my]], which [[tools/wasm/myla.mjs]] instantiates afresh for each call (`call`: one program per instance), so nothing there runs a second program after it.
- Callgrind, `MYLA_THREADS=1`, the CLI built by `build/myla build selfhost/main.my` from BASE's sources and from this branch's (2026-11-18, BASE 3add216): an empty program's `myla run` 24,289,559 instructions before, 22,930,622 after (−1,358,937, 5.6 percent); a hello world's 24,323,961 before, 22,964,527 after. In a `-g` build, `myla___walkd_interp$Interp` (2,212,260 inclusive before) is gone from the profile. `myla check` is unchanged (21,402,110 before, 21,402,214 after).
- [[tests/burn/test_check_cost.py]]: `run`'s bound lowered from 26.7 M to 25.3 M, 10 percent over the new count (D283); it passes. The saving is under the 10 percent headroom, so the old count would pass the new bound too: the counts above are the before and after.
- The program's output and status are as before: `myla run hello.my` prints `hello` with status 0; a program printing a line and then calling `process.exit(3)`, piped into `cat`, prints its line and ends with 3. `scripts/bootstrap.sh` reaches its fixed point.
