---
id: MYLA-929
title: "Programs built for aarch64 run about 5× slower than x86-64's on a comparable machine"
type: bug
status: backlog
priority: medium
labels: [aarch64, performance, codegen]
---
Found by [[MYLA-926]]'s first native runs on `ubuntu-24.04-arm` (2026-11-22, `7725ae0`, CI run 45011729950). The same work on GitHub's 4-vCPU runners of each architecture:

| Work | x86-64 (`ubuntu-24.04`) | aarch64 (`ubuntu-24.04-arm`) | Ratio |
|---|---|---|---|
| The bootstrap, stages 0–3 to the fixed point (the compiler compiling itself, one process) | 12 s (`scripts/bootstrap.sh build`) | 69 s (`just bootstrap`) | 5.7× |
| `test_std_modules` | about 109 s, the suites one at a time | 980 s, four suites at once | about 9× |
| `test_test_native` | about 163 s | 1,171 s | about 7× |
| `test_lsp` | about 46 s | 464 s | about 10× |

The suites' ratios include four suites sharing four cores on aarch64 (`scripts/test-target.py host`); the bootstrap's doesn't, and is the cleaner measure. The two runners' processors are of one class (cloud vCPUs), so a factor of five is the code, not the machine: the aarch64 back end ([[MYLA-163]]) allocates registers more simply than x86-64's, and [[MYLA-826]] measured its frames. Interpreted, `num`'s case `pow10_sig_is_exact` (15.8 s on x86-64) ran past its 60 s limit there; MYLA-926 made the case linear (10.3 s on x86-64).

- [ ] Measure where the time goes: a profile (`perf record`) of the bootstrap's stage 2 on an aarch64 machine, against x86-64's
- [ ] The largest causes fixed, or tasks for them
- [ ] The bootstrap's ratio again, after
