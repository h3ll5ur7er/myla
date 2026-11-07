---
id: MYLA-362
title: "wasm32: list_dir returned short lists after 64 directory opens"
type: bug
status: review
priority: medium
labels: [wasm, fs]
---
Found by the `std.glob` lane ([[MYLA-326]]). `platform_wasm.dir_read` keeps each descriptor's readdir cookie in slot `fd & 63` of `__wasi_cookies`, and `open_dir` never reset it. Node's shim doesn't reuse descriptor numbers, so after 64 opens a new descriptor found an old cookie, and `fs.list_dir` gave a short or empty list. Under Node, listing two directories 40 times each gave `6 3` for 32 rounds, then `0 0`. A runtime that reuses numbers could hit it from the second listing on.

- [x] `open_dir` zeroes its descriptor's slot ([[lib/std/platform_wasm.my]], commit `da0278a`)
- [ ] A burn test in the wasm32 target suite: 100 listings of the same directories, each count unchanged
