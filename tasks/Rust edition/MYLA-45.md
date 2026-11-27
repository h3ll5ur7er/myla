---
id: MYLA-45
title: Rust test suite checks too little
type: improvement
status: done
priority: medium
labels: [rust, tests]
---
- [ ] The interpreter unit tests only assert exit code 0 and let stdout spill into the log (`myla-interp/src/lib.rs`) (dropped: the Rust edition was removed, [[MYLA-70]])
- [ ] `examples/io.my` isn't covered by any test (dropped: the Rust edition was removed, [[MYLA-70]])
- [ ] The native/interpreter differential runs 3 hand-picked programs; the README calls it "asserts native matches" (dropped: the Rust edition was removed, [[MYLA-70]])
- [ ] No tests for sema, codegen or the CLI binary beyond `tests/cli.rs` (dropped: the Rust edition was removed, [[MYLA-70]])

**Closed without a fix:** the Rust edition was removed from the repository ([[MYLA-70]]); its code is in git history (commit `043acb9`). See [[Architecture/Rust-edition]].
