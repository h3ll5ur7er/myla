---
id: MYLA-610
title: "Two library comments weigh an import by what checking it cost before the lazy modules"
type: chore
status: todo
priority: low
labels: [std, comments, check-time, round-6]
---
Found by [[Project/Review-2026-11-12]] (the line on [[MYLA-554]]: the comments that keep helpers private "for the import cost" were measured before lazy modules, now 1.7 percent) and listed by [[MYLA-554]], which edits no `.my` file. Two comments in `lib/std/` quote a check cost measured before the loader read a library module's bodies only once called ([[MYLA-359]], [[MYLA-412]], [[MYLA-413]]):

- [[lib/std/task.my#L498-L502]], above `Fifo`: "(`std.deque` would do, but importing it costs every program that imports `std.task` about 2.5 ms of checking.)" (written with [[MYLA-351]])
- [[lib/std/time.my#L28-L32]], above `pad`: "Not `std.fmt`'s own: importing it and `std.num` would cost every program that imports `std.time`, `std.test` among them, 16 ms of checking." (written with [[MYLA-334]])

The comments of the same kind that [[MYLA-553]] wrote already give a figure measured with the lazy modules ([[lib/std/fs.my#L735-L738]], [[lib/std/net.my#L1727-L1730]], [[lib/std/archive.my#L1076-L1080]], [[lib/std/compress.my#L2402-L2406]]), and so does [[selfhost/checker.my#L4480-L4485]].

Measured by [[MYLA-554]] on `2ceef83` (`valgrind --tool=callgrind`, `build/myla check` with the library the tool carries, instructions of the whole run):

| Program | Instructions | Added |
| --- | --- | --- |
| `fun main() {}` | 20.7 M | |
| `import std.task as task` | 25.2 M | |
| … and `import std.deque as deque` | 26.2 M | 1.0 M, 3.9 % |
| … and `deque.new()`, `push_back`, `pop_front` called | 27.6 M | 2.4 M, 9.4 % |
| `import std.time as time` | 29.8 M | |
| … and `import std.fmt as fmt`, `import std.num as num` | 45.1 M | 15.2 M, 51 % |

So the reason in std.time's comment still holds (its 16 ms is stale: about 15 M instructions now, 3 to 5 ms by wall time on the shared container), and std.task's is weaker than it says (about 1 M instructions for the import, 2.4 M with what `Fifo` would call). The review's 1.7 percent is its own figure, and it doesn't say which import it measured.

- [ ] Each comment gives a figure measured with the lazy modules (instructions and a percentage, as [[MYLA-553]]'s do), or goes with its reason
- [ ] For `std.task`'s `Fifo`: decide whether `std.deque` now does (its import with the calls `Fifo` makes, against `Fifo`'s own code)
