---
id: MYLA-153
title: A faster burn suite and honest test timings
type: improvement
status: todo
priority: medium
labels: [testing, ci]
---
Split from [[MYLA-58]], whose tiers worked once: the burn suite has grown to 811 tests and takes about 4 minutes in CI (about 110 s outside the self-hosted gates), while [[Development/Testing]] promises a fast tier of about 20 s and contradicts itself on the timings.

- [ ] Measure where the burn time goes (per module) and keep the slow, broad corpora (concurrency stress, the language server scenarios, the JSON corpus, the self-hosted gates) out of the fast tier
- [ ] Testing.md's timings measured again and made consistent
