---
id: MYLA-817
title: "`myla run` releases the whole interpreter before it exits"
type: improvement
status: todo
priority: low
labels: [interpreter, performance]
---
Found by [[MYLA-792]] while measuring the start-up. At the end of `myla run`, `cmd_interp` ([[selfhost/driver.my]]) returns its status and so releases the interpreter, the checker and the program it holds, value by value, just before the process exits: under callgrind, `myla run` of an empty program spends 2.6 M of its 29.3 M instructions in the release walk of `Interp` (`myla___walkd_interp$Interp`, 2,638,374 instructions; 2026-11-17 on `fe30af6` with [[MYLA-792]]'s lazy constants).

```myla fragment
fun main() {
}
```

`valgrind --tool=callgrind build/myla run empty.my`, then `callgrind_annotate --inclusive=yes` (with `build/myla build -g selfhost/main.my` for the names).

- [ ] `myla run` ends with the program's status without releasing what the process gives back anyway (an `exit` where `cmd_interp` has its status, or a release the runtime skips at the end), in every caller of `cmd_interp` (the CLI, the playground's `play_main.my`, which may run more than one program in a process)
- [ ] The instruction count of an empty program's `myla run`, before and after, pinned with date and hash (D197)
