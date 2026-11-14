---
id: MYLA-709
title: "Windows step 10: bootstrapping on Windows"
type: feature
status: backlog
priority: low
labels: [platforms, windows]
---
A step of [[MYLA-165]], the Windows target, in the plan the owner accepted on 2026-11-14 ([[Project/Follow-up-plan#windows-2026-11-14]]). D213 (second phase): a third seed, `bootstrap/seed-windows.s` (cheap under D207), and the bootstrap run on Windows with Git Bash and LLVM's tools.

- [ ] `scripts/bootstrap.sh` on Windows (Git Bash), the seed found by `scripts/host.sh`
- [ ] `bootstrap/seed-windows.s` from `scripts/update-seed.sh`, checked by the Windows runner's bootstrap
