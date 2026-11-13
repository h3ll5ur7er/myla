---
id: MYLA-43
title: Rust edition language gaps
type: feature
status: done
priority: low
labels: [rust]
---
Parsed but ignored, or missing:

- [ ] `import`/`from` (no module system), `pub`, `typealias`, generic bounds (dropped: the Rust edition was removed, [[MYLA-70]])
- [ ] `#derive` is accepted and does nothing (dropped: the Rust edition was removed, [[MYLA-70]])
- [ ] Trait declarations are skipped, so default methods don't work ("no method `hi` on `S`") (dropped: the Rust edition was removed, [[MYLA-70]])
- [ ] Compound assignment: the AST has `Assign.op`, but the parser only recognises `=` (dropped: the Rust edition was removed, [[MYLA-70]])
- [ ] Negative-literal and float patterns (dropped: the Rust edition was removed, [[MYLA-70]])
- [ ] Ranges as values (`0..3` only works as a `for` head) (dropped: the Rust edition was removed, [[MYLA-70]])
- [ ] Recursive closures (a closure captures its environment before its own binding exists) (dropped: the Rust edition was removed, [[MYLA-70]])
- [ ] Exhaustiveness checking (dropped: the Rust edition was removed, [[MYLA-70]])
- [ ] `sort`, `join`, `reduce` and similar list functions (dropped: the Rust edition was removed, [[MYLA-70]])
- [ ] `push`/`pop`/`insert`/`remove` are intercepted by name before user methods, so user types can't define them; they also work on `let` bindings, against `stdlib.md` (dropped: the Rust edition was removed, [[MYLA-70]])

**Closed without a fix:** the Rust edition was removed from the repository ([[MYLA-70]]); its code is in git history (commit `043acb9`). See [[Architecture/Rust-edition]].
