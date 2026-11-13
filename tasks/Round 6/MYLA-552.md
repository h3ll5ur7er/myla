---
id: MYLA-552
title: "R10 Check time and the seeds: under 5 ms, code that doesn't depend on what was read, labels per function"
type: improvement
status: todo
priority: medium
labels: [loader, performance, seed, bootstrap, round-6]
---
Work package R10 of [[Project/Review-2026-11-12]]. Files: `selfhost/loader.my`, `selfhost/astcache.my`, `selfhost/lower.my` (`find_kept_params`), `scripts/update-seed.sh`, `scripts/bootstrap.sh`. Follows [[MYLA-359]], [[MYLA-412]], [[MYLA-431]] and [[MYLA-432]]; after [[MYLA-545]], which shares the loader.

Measured on `547339a` (before round 5 in brackets): `myla check` of a hello world 21.2 M instructions and 6.1 ms (39.4 M, 8.7 ms); with std.io 37.0 M and 9.8 ms (101 M, 22.6 ms); with std.http 146 M and 35 ms (394 M, 97 ms). `build/myla` grew from 5.13 to 6.23 MB and `selfhost/embedded_std.my` from 2.33 to 3.12 MB.

- [ ] [[MYLA-359]]'s last box: a hello world under 5 ms, or the reason it stays at 6
- [ ] **The generated code depends on which library bodies were read**: `find_kept_params` votes over the loaded bodies, so 13 of 109 programs build different code lazily and eagerly (their output is equal). Make the vote independent of what was read
- [ ] A switch that reads every body eagerly, as an oracle for the lazy load (none exists; the review built a compiler for it)
- [ ] `scripts/update-seed.sh` checks every `lib/std` module whole: all are lazy now, and `test_std_modules` only covers modules with cases
- [ ] **A seed update still costs the pack about 2.9 MB** (908 KB and 2,019 KB): the labels renumber, so 197,956 lines differ where 40,108 do with `.L` labels normalised. Number the labels per function
- [ ] `seed_compile` rewrites `selfhost/embedded_std.my` in the working tree while it runs; write it elsewhere, or restore it
