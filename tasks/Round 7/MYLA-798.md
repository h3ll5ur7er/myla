---
id: MYLA-798
title: "R7-9 Windows: many-children's 393 of 400 (H12), env's case and batch names (M13), the deferred close, long paths"
type: bug
status: todo
priority: high
labels: [platforms, windows, round-7]
---
Work package of [[Project/Review-2026-11-17]], lane "Windows" (section 5). Files: `lib/std/platform_windows.my`, `lib/std/process.my`, `scripts/windows-runner.py`, `.github/workflows/ci.yml`'s `windows` job. The reproducers are in the review's bundle (`repro-r6/`, with a README per area); each fix turns its reproducer into a test that fails before it. The owner's decisions it builds as the review recommends: 7. New tasks it files take ids 861–868.

- [ ] **H12** (high, real Windows only, cause unknown): `process/many-children` on 16 workers counted 393 of 400 on master's run (CI run 246); not reproduced in 54 runs under Wine; the program prints only a count, and `collect_async` treats a read error on the child's pipe as its end. First a case that prints each failure, the runner showing stderr, then a rate on `e153ee08` and `1e6397ff` (CI's `windows` job can run it). `repro-r6/windows-library/many_children_diag.my`. Reopens [[MYLA-705]]
- [ ] **M13**: `env("MYLA_VAR")` doesn't find `MyLa_Var`; the system's `Path` isn't `env("PATH")`; `is_batch` tests only the suffix, so `x.bat.` gets C-runtime quoting (CVE-2024-43402's hole). `env_case.my`, `bat_trailing_dot.my`
- [ ] [[MYLA-706]]'s follow-up: the deferred close has no limit
- [ ] Decision 7: long paths: prefix `\\?\` as Rust does
- [ ] [[MYLA-704]]/[[MYLA-707]]/[[MYLA-708]]'s follow-ups: `join` on verbatim paths; the console's code page after a default Ctrl-C; the runner's report can't diagnose a failed process case
- [ ] [[MYLA-700]]/[[MYLA-702]]/[[MYLA-716]]/[[MYLA-757]]'s follow-ups: `myla check --target` isn't accepted; D254 fails under the Node host for sockets and block devices; `debug/dwarfdump` never runs on the runner (no `llvm-dwarfdump` in the image)
- [ ] [[MYLA-754]]'s box: `SOCKETS` on 16 workers measured on CI's runner before and after
- [ ] Low: `SpawnError.Other(193)` prints "errno 193" ([[MYLA-770]]); `map_memory` commits what it reserves (several hundred MiB on 32 CPUs); the suites don't set a UTF-8 locale for Wine
