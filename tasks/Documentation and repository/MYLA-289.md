---
id: MYLA-289
title: "A seed policy: one seed per pull request, or seeds out of the history"
type: improvement
status: backlog
priority: high
labels: [bootstrap, repository, decision]
---
Found by the review of 6 November 2026 ([[Project/Review-2026-11]]). 153 x86-64 and 44 aarch64 seed versions were committed in six days, 60 percent of the commits, against the docs' "one per pull request": they account for 110 of the 117 MB pack (433 KB per x86-64 version, 991 KB per aarch64 one, packed), where the repository was 3.5 MB in October. At this rate a year is several gigabytes. A bootstrap needs only the latest seed; nothing needs the history.

- [ ] A decision: squash the seed to one version per pull request on merge (the hook and CI check only the tip); and/or shrink the aarch64 seed ([[MYLA-257]]); and/or keep seeds out of the tree (Git LFS, release assets) with their hashes in it
- [ ] [[Development/Bootstrap]] says what the policy is and what a seed costs
- [ ] The `backup/python-toolchain-final` branch, the root of the seed chain, tagged, and the first seed's hash recorded
