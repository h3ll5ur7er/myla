---
id: MYLA-45
title: Rust test suite checks too little
type: improvement
status: backlog
priority: medium
labels: [rust, tests]
---
- [ ] The interpreter unit tests only assert exit code 0 and let stdout spill into the log (`myla-interp/src/lib.rs`)
- [ ] `examples/io.my` isn't covered by any test
- [ ] The native/interpreter differential runs 3 hand-picked programs; the README calls it "asserts native matches"
- [ ] No tests for sema, codegen or the CLI binary beyond `tests/cli.rs`
