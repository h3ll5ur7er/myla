---
id: MYLA-312
title: "#test cases run natively (the evidence for MYLA-303's step 4)"
type: improvement
status: backlog
priority: medium
labels: [testing, native]
---
Found by Advent of Code ([[Project/AoC-2015-2021]], F3). `myla test` runs the cases in the interpreter, so a case that is fast as a binary can be far too slow as a test. This task holds the evidence. The design is step 4 of [[MYLA-303]] (`myla test --native` and `--target`), which is in the owner's hands, and this task is closed by that step.

## Evidence

- The two small examples of 2020 Day 17 take 7.1 s under `myla test`. The built binary does both parts of the larger real input in 12 ms.
- 6 of the 175 days had their examples moved out of `#test`, or never put there, and were checked by hand through the binaries. So the code that shipped was not the code that was tested.
- The interpreter is about 500 times slower than native code on `fib(30)` ([[MYLA-317]]), and its maps are linear ([[MYLA-310]]).

- [ ] Closed by [[MYLA-303]]'s step 4, if decided, or by its own decision otherwise
