---
id: MYLA-504
title: "A program importing std.process is built with the task runtime, for a test function of std.process"
type: bug
status: todo
priority: low
labels: [codegen, concurrency, check-time, round-5]
---
Found by [[MYLA-432]] (P18). A native build gets the executor and its frames (`CodeGen.frames`, D90) when `Checker.task_line` is set: an `async let` in any body checked. Before MYLA-413 every body of every loaded module was checked, so a program that imports `std.process` (or `std.task`, `std.http`) became a program with tasks because of one of their bare `#test` functions (`input_written_while_output_read` in std.process has two `async let`s), which no program ever runs: an imported module's test functions are never the program's.

```myla fragment
from std.process import exit

fun main() {
    print(1)
}
```

Built natively: 37,584 bytes with `__sched_init` and the workers; the same program without the import, 18,768 bytes. `examples/stdio`, `args`, `readfile` and `subprocess` are built so.

MYLA-432 kept the code byte-identical when the bodies became lazy: the loader still finds an `async let` in any body it left unread (`LazyTable.task_line`) and the build has tasks as before. The fix is to count only the bodies the checker read: drop `LazyTable.task_line` and `LazyBodies.task_line`, so that `task_line` is the checker's alone (an `async let` reached from `main`, or in a function the program calls). The four examples then shrink by half and start no workers.

- [ ] Decide whether a library's unreached `async let` should make a program one with tasks (recommended: no)
- [ ] If not, drop `LazyTable.task_line` and pin the four examples' binaries without the executor in a burn test
