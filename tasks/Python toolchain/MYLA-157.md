---
id: MYLA-157
title: Check a leak when ? fails inside a list or map literal (Python backend)
type: bug
status: backlog
priority: low
labels: [python-backend, memory]
---
[[MYLA-4]] notes that in the Python backend, a `?` that returns early from inside a list or map literal leaves the literal's elements allocated so far unreleased; no task tracks it, and it wasn't measured. (The self-hosted backend's leaks went with [[MYLA-22]].)

- [ ] Reproduce with a stress program that fails a `?` inside a literal many times, measuring memory
- [ ] If it leaks: release the staged elements on the early way out, as the staging of call arguments does
