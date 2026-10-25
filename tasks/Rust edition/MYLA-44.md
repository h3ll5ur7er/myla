---
id: MYLA-44
title: Unused Rust dependencies and docs that claim them
type: chore
status: backlog
priority: low
labels: [rust, cleanup, docs]
---
No `.rs` file uses these declared dependencies:

- [ ] `ariadne` (myla-syntax, myla-cli): diagnostics use a custom caret renderer
- [ ] `ahash`, `crossbeam-deque`, `parking_lot` (myla-runtime)
- [ ] `target-lexicon` (myla-codegen)

And the docs say otherwise: `docs/concurrency.md` mentions `parking_lot` locks (it's `std::sync::Mutex`), the workspace manifest says ahash hashes the map runtime (it's `DefaultHasher`), `changes-from-original.md` lists ariadne.

- [ ] Remove the dependencies or use them, and fix the docs
- [ ] `"chan"` in the builtin list is dead (it's a keyword); `println` is undocumented
