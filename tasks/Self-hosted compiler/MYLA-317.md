---
id: MYLA-317
title: "The interpreter's speed"
type: improvement
status: backlog
priority: low
labels: [interpreter, performance]
---
Found by Advent of Code ([[Project/AoC-2015-2021]], F8). On master `d5d80bc`, `fib(30)` takes 3,686 ms under `myla run` and 7 ms natively, about 500 times slower (the agent measured 730 times on an earlier build). Native speed is excellent, so this matters mainly through `#test` ([[MYLA-312]]) and for `myla repl`. Maps make it worse: in the interpreter they are two lists searched linearly ([[MYLA-310]]).

Before choosing a fix, a profile of where the time goes: environment lookups by name, `Value` boxing and copying, the dispatch over the tree. Then the candidates, cheapest first: variables resolved to slots when a function is first entered, hashed maps, and, if the gap is still large, a bytecode form of the checked tree.

- [ ] A profile of `fib` and of a map-heavy and a string-heavy program under `myla run`
- [ ] The fixes it points to, each measured

Measured while fixing PR #46's CI (2026-11-08): `run_async`'s copy of 200 KB of a child's output, a loop of `out.push(chunk[i] as uint8)` in `std.process`, takes about 1.35 s under `myla run` on master and 1.5 s after wave 2 (about 12 % slower). `test_time`'s process program timed its whole run against 3 s and went over on CI; it now times only the timeout it guards. A primitive for `str` to `[uint8]` ([[MYLA-369]]) would take that loop out of interpreted code entirely.
