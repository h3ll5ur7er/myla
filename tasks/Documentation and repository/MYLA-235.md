---
id: MYLA-235
title: "CI: the burn suite against the bootstrapped build/myla and build/myla-lsp"
type: improvement
status: todo
priority: medium
labels: [ci, tests]
---
D115 ([[MYLA-216]]): today pull-request burn tests run the CLI and language server built by the Python backend, and only the bootstrap job runs the real `build/myla`, on `hello.my`. The burn job bootstraps (from the seed once [[MYLA-218]] lands) and runs the suite against `build/myla` and `build/myla-lsp`.

- [ ] The bootstrap measured on a CI runner; in the burn job, or shared as an artifact if it costs too much
- [ ] The burn tests pick up `build/myla` and `build/myla-lsp`; CI's job times before and after
