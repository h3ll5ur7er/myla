---
id: MYLA-944
title: "A wasm32 harness under Node on a Windows host can't use its case's scratch directory: a Windows path in a POSIX shim"
type: bug
status: backlog
priority: medium
labels: [wasm, windows, test]
---
Found by [[MYLA-926]] step 2's port of the burn suites (2026-11-24, group E), in the native Windows run 277: `test_test_native.TestWasm32.test_the_scratch_directories_go` reports `FAIL  passes_and_cleans: runtime error: t…` (the case's `test.temp_dir()` failing) where Linux passes.

`myla test --target wasm32-wasi` runs the harness itself (MYLA-370), each run with `MYLA_TEST_DIR` under its scratch directory, `scratch_dir()`: on Windows `%TEMP%\myla-test-<n>/run<k>`, a Windows path. The module runs under `tools/wasm/run.mjs`, whose WASI shim (`wasi.mjs`, `node_fs.mjs`) sees the host's `/` as its root and joins a path that doesn't start with `/` onto `PWD`: `C:\Users\…` is no path it can make. Every other TestWasm32 test, which uses no scratch directory, passes on the Windows runner.

What fixes it is the shim's business (the wasm agent's area): either the shim maps a Windows host's drive paths (`C:\…`, `C:/…`) to host paths, or `myla test` hands a wasm32 harness its directories as the shim names them. Until then the test fails on Windows (it is not skipped).

- [x] Decide where the mapping lives (the owner, 2026-11-24: the lead makes it, in the shim): on Windows a wasm program names a host path on any drive `/X:/p`, which `tools/wasm/node_fs.mjs`'s `hostPath` gives Node as `X:/p` before each call (`/p` without a drive is the working directory's drive's, as before); the driver gives a wasm32 harness its `MYLA_TEST_DIR` so (`wasi_name`). On Linux both are the identity: test_test_native, test_wasm and test_selfhost_parser pass, and wasm32's test_stdio and test_fs
- [ ] TestWasm32.test_the_scratch_directories_go passes on the `burn-windows` job

The lead's look (2026-11-24): the driver can't hand the harness its directory without the drive, as MYLA-940's runner and test_wasm's `under_the_runner` name paths (`/Users/…`): on the CI runner `%TEMP%` is on C: and the checkout, Node's working directory, on D:, and Node reads `/x` from the working directory's drive. Proposed (for the owner and the wasm area's agent): on Windows a wasm program names a host path `X:\p` as `/X:/p`, the shim's NodeFs maps a path `/X:/…` to `X:/…` before each `fs` call (a `/x` without a drive as today), `run.mjs`'s `PWD` and the driver's `MYLA_TEST_DIR` are given so, and test_wasm's `under_the_runner` writes that spelling. Every drive is then reachable, not only the working directory's.
