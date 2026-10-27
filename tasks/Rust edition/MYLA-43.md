---
id: MYLA-43
title: Rust edition language gaps
type: feature
status: done
priority: low
labels: [rust]
---
Parsed but ignored, or missing:

- [ ] `import`/`from` (no module system), `pub`, `typealias`, generic bounds
- [ ] `#derive` is accepted and does nothing
- [ ] Trait declarations are skipped, so default methods don't work ("no method `hi` on `S`")
- [ ] Compound assignment: the AST has `Assign.op`, but the parser only recognises `=`
- [ ] Negative-literal and float patterns
- [ ] Ranges as values (`0..3` only works as a `for` head)
- [ ] Recursive closures (a closure captures its environment before its own binding exists)
- [ ] Exhaustiveness checking
- [ ] `sort`, `join`, `reduce` and similar list functions
- [ ] `push`/`pop`/`insert`/`remove` are intercepted by name before user methods, so user types can't define them; they also work on `let` bindings, against `stdlib.md`

**Closed without a fix:** the Rust edition was removed from the repository ([[MYLA-70]]); its code is in git history (commit `043acb9`). See [[Architecture/Rust-edition]].
