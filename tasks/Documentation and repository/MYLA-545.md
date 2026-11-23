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
- [x] `benchmarks/fft/run.sh`: builds, compares the answers, prints the medians
- [x] The result on [[Development/Benchmarks]]

## Evidence

`benchmarks/fft/run.sh 7` on 2026-11-23 (a shared 4-CPU cloud VM, gcc 13.3, commit `ad442de`): "All checksums and errors identical: fft-4096 121774412 6217, fft-1048576 237801659848 20". Medians, and the time by C's at `-O2` in the same layout:

| | 4096 points, 10,000 round trips | | 1,048,576 points, 10 round trips | |
| --- | --: | --: | --: | --: |
| C, two arrays, `-O2` | 0.97 s | 1.00 | 1.85 s | 1.00 |
| C, structs, `-O2` | 0.79 s | 1.00 | 1.69 s | 1.00 |
| C, two arrays, `-O3 -march=native` | 0.89 s | 0.92 | 2.16 s | 1.17 |
| C, structs, `-O3 -march=native` | 0.70 s | 0.89 | 0.91 s | 0.54 |
| Myla, two lists | 3.92 s | 4.03 | 3.06 s | 1.65 |
| Myla, list of `Complex` | 4.33 s | 5.49 | 3.11 s | 1.84 |

The small size is steady (each variant within 10 % over two samples of 5 and 7 runs); the large one is bound by memory and varied by up to 1.8 times between runs of one binary, so its ratios are rough: by the fastest runs 1.5 (lists) and 2.5 (structs). `build/myla test`: 2/2 and 3/3 passed. Instructions at 4096 points, 200 round trips (callgrind): Myla 1,839 M (lists) and 1,932 M (structs), C at `-O2` 361 M.
