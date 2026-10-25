---
id: MYLA-69
title: Continuous integration with GitHub Actions
type: chore
status: review
priority: high
labels: [ci, tests]
---
Run the test suites and the bootstrap on every pull request and on pushes to `master`: `.github/workflows/ci.yml`.

- [x] `unit`: unit and integration tests on Python 3.12 and 3.13 (both pass locally)
- [x] `burn`: the burn suite on Python 3.12 (native builds with the runner's binutils)
- [x] `bootstrap`: `scripts/bootstrap.sh`, then the stage 3 compiler builds and runs `examples/hello.my`
- [ ] First run on GitHub. The `burn` job will be red until [[MYLA-4]] is fixed (5 failing self-hosted checker subtests); that is the suite being honest, not a CI problem
- [ ] The `bootstrap` job takes about 6 minutes today; about 15 seconds once [[MYLA-60]] and [[MYLA-16]] land
- [ ] Optional: cache nothing (there are no dependencies); add a Rust job only if the Rust edition stays ([[MYLA-70]])
- [ ] Mention the badge and the jobs on [[Development/Testing]] once it runs
