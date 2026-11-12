---
id: MYLA-543
title: Compare Myla with other languages on benchLANG
type: chore
status: review
priority: medium
labels: [benchmarks]
---
Measure Myla against the 22 runtimes of [benchLANG](https://github.com/GlebOlsen/benchLANG) (six workloads: primes, recursive Fibonacci, strings, Mandelbrot, binary trees, k-nucleotide; runtime, peak memory, binary size, compile time), and present the result. Done means: an idiomatic Myla version of every workload whose checksums match the other languages', one full run of the suite with Myla in it, and a graphical report.

- [x] `benchmarks/benchlang/bench.my`: the six workloads, with `#test` cases checked against benchLANG's Python version at small sizes
- [x] Myla registered in benchLANG's runner (`myla build bench.my -o bench && strip bench`)
- [x] The whole suite run, two runs per language, with the toolchains its Nix flake pins
- [x] Report page built from the results file
- [x] Wiki: [[Development/Benchmarks]] says how to repeat it and what it showed

## Evidence

The run of 2026-11-12 (`benchmarks/benchlang/results-2026-11-12.txt`): 23 runtimes, two runs each, no failure, "All checksums identical across languages". Myla: 11.03 s in total, 16th of 23 (C 3.42 s); compile 0.21 s, the fastest native build; binary 71 KiB; peak 54 MiB. `build/myla test benchmarks/benchlang/bench.my`: 12/12 passed. The numbers and what they showed: [[Development/Benchmarks]].

Found on the way: `int32` division goes through the 64-bit `idiv`, behind checks of the divisor; the primes workload takes 1.16 s where most runtimes take 0.69 s. How much of the gap each part costs is not measured yet.
