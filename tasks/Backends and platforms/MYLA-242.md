---
id: MYLA-242
title: "Benchmarks: the gap to C"
type: improvement
status: todo
priority: medium
labels: [performance, backend, design]
---
The first input of [[MYLA-160]], de-risking D117: how far Myla's native code is from C, and where the time goes. D117 (4) brings LLVM back only if measurements show a gap the IR can't close; this task provides them.

- [ ] A small benchmark set, each program in Myla and in C doing the same work: integer loops and arithmetic, floats, recursion and calls, lists (push, index, iterate), maps, strings and builders, structs and enums, closures, generic code, and one program of many small tasks (D92)
- [ ] Run against `cc -O0` and `cc -O2`: time, instructions, peak memory; the Myla binaries also against the interpreter's output, so the set doubles as a test
- [ ] Where Myla's time goes, per program: reference counting, copy-on-write, bounds checks, the calling convention, frame traffic, the runtime's routines (`perf` where it helps)
- [ ] A script in the repository that reruns it, and the results on a wiki page, with what each gap would need: an IR optimisation (D117 (3)), a runtime change, or nothing
