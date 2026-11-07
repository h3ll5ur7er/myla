---
id: MYLA-289
title: "A seed policy: one seed per pull request, or seeds out of the history"
type: improvement
status: review
priority: high
labels: [bootstrap, repository, decision]
---
Found by the review of 6 November 2026 ([[Project/Review-2026-11]]). 153 x86-64 and 44 aarch64 seed versions were committed in six days, 60 percent of the commits, against the docs' "one per pull request": they account for 110 of the 117 MB pack (433 KB per x86-64 version, 991 KB per aarch64 one, packed), where the repository was 3.5 MB in October. At this rate a year is several gigabytes. A bootstrap needs only the latest seed; nothing needs the history.

- [x] A decision: squash the seed to one version per pull request on merge (the hook and CI check only the tip); and/or shrink the aarch64 seed ([[MYLA-257]]); and/or keep seeds out of the tree (Git LFS, release assets) with their hashes in it
- [x] [[Development/Bootstrap]] says what the policy is and what a seed costs
- [x] The `backup/python-toolchain-final` branch, the root of the seed chain, tagged, and the first seed's hash recorded

## Evidence

- D156 (the owner's decision): one seed per pull request, in its last commit; staging commits excepted.
- [[Development/Bootstrap]] ("When to update it", "What a seed costs", "The first seed", the hook), [[Development/Conventions]], `AGENTS.md` and the `myla` skill say so. `.githooks/pre-push` stops a push to `master` or `main` with a stale seed and only reminds on another branch (tried both ways: exit 1 and 0).
- The first seed is recorded in [[Development/Bootstrap#the-seed]]: commit 74e97c8, compiled from a2f95ba (whose stage 1 `backup/python-toolchain-final`, d94f948, built), SHA-256 `7202f99a1d0031add5c0962830e0d2d5dd5b84a9142b701ee07dc07c7237d045`. The owner tagged it: `python-toolchain-final` is d94f948 on GitHub (2026-11-07).
