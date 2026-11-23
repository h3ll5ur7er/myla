---
id: MYLA-545
title: Measure Myla on an FFT
type: chore
status: review
priority: low
labels: [benchmarks]
---
How far Myla is from C on a fast Fourier transform, the textbook iterative radix-2 one, in the two layouts a user would write: two lists of floats, and one list of a `Complex` struct with the operator traits. Done means: both in Myla, the same in C, results equal bit for bit, and the times.

- [x] `benchmarks/fft/fft_split.my` and `fft_complex.my`, with `#test` cases (the checksum checked against a naive DFT)
- [x] `benchmarks/fft/fft.c`, both layouts (`-DCOMPLEX`)
- [x] `benchmarks/fft/csharp/Program.cs` and `benchmarks/fft/fft.py`: the same in C# (the base library only) and in plain Python (no NumPy), both layouts each
- [x] `benchmarks/fft/run.py`: builds, requires equal answers, times the round trips alone, writes a results file
- [x] `benchmarks/fft/report.html`, filled by `report.py`: the results as charts and a table, with every source in a section that opens
- [x] The result on [[Development/Benchmarks]]

## Evidence

`python3 benchmarks/fft/run.py --runs 5` on 2026-11-23 (`benchmarks/fft/results-2026-11-23.json`): "check 4096 points, 3 round trips: all 10 variants print [121774412, 1]", "check 65536 points, 2 round trips: all 10 variants print [7207693291, 2]", and one checksum per size from every timed run. At 4096 points, nanoseconds for one butterfly: C `-O2` 2.10 (two arrays) and 2.08 (structs), C# 3.18 and 2.30, Myla 7.95 and 8.81 (3.8 and 4.2 times C), Python 293 and 320. The table and the large size: [[Development/Benchmarks]]. The checksum at 8 and at 1024 points is a naive DFT's (Python's `cmath`). `build/myla test`: 2/2 (`fft_split.my`) and 3/3 (`fft_complex.my`) passed. Instructions at 4096 points, 200 round trips (callgrind): Myla 1,839 M (lists) and 1,932 M (structs), C at `-O2` 361 M.

A first measurement the same day with gcc 13.3 and whole-program times gave 4.0 and 5.5 times C at 4096 points.
