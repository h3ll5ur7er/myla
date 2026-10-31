---
id: MYLA-156
title: CI maintenance - gdb in the burn job, actions off Node 20
type: chore
status: todo
priority: medium
labels: [ci]
---
Found while triaging the review tasks ([[MYLA-69]], [[MYLA-99]]):

- [ ] The burn job installs no gdb, so the 23 gdb tests of `tests/burn/test_debug_info.py` and both of `tests/burn/test_vscode_debugger.py` are always skipped in CI: install it (`apt-get install gdb`)
- [ ] The green master run warns that `actions/checkout@v4`, `setup-node@v4`, `setup-python@v5` and `upload-artifact@v4` are being moved off Node 20, and that `ubuntu-latest` is moving to a new release: update the actions and pin what needs pinning
