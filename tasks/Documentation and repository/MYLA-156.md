---
id: MYLA-156
title: CI maintenance - gdb in the burn job, actions off Node 20
type: chore
status: done
priority: medium
labels: [ci]
---
Found while triaging the review tasks ([[MYLA-69]], [[MYLA-99]]):

- [x] The burn job installs no gdb, so the 23 gdb tests of `tests/burn/test_debug_info.py` and both of `tests/burn/test_vscode_debugger.py` are always skipped in CI: install it (`apt-get install gdb`)
- [x] The green master run warns that `actions/checkout@v4`, `setup-node@v4`, `setup-python@v5` and `upload-artifact@v4` are being moved off Node 20, and that `ubuntu-latest` is moving to a new release: update the actions and pin what needs pinning

## Evidence

- The burn job installs gdb and runs on the runner's own Python 3.12 (as the extension job does: `actions/setup-python` would make gdb embed its libpython, and the binaries' pretty-printers wouldn't run); it caches `build/test-tools` (keyed on the same sources as `tests/burn/_tools.py`'s hash) and the tree-sitter npm install (`setup-node`'s npm cache) for [[MYLA-192]].
- Every runner pinned to `ubuntu-24.04`; the actions at their current majors (checkout, setup-python, setup-node, upload-artifact v7, cache v6, all on Node 24). Their notes for v5 to v7 change nothing this workflow uses (no `registry-url`, `always-auth` or `pull_request_target`).
- Not run yet: CI runs on pull requests and pushes to `master`, so the next pull request is the first run of this workflow. Locally, with gdb installed, all 32 tests of `test_debug_info.py` run and pass, none skipped.
