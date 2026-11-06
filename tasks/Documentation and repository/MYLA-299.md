---
id: MYLA-299
title: Examples and doc blocks for the November features
type: chore
status: todo
priority: medium
labels: [docs, examples]
---
Found by the review of 6 November 2026 ([[Project/Review-2026-11]]). No file in `examples/` uses any of the sixteen features of the November round (`defer`, `if let`, `while let`, slices and `^`, format specs and `Format`, `+=`, `if` expressions, let-else, default parameters, the unit type, `std.math`, `std.time`, `task.sleep`/`timeout`/`yield`), and the reading order in [[Getting started]] ends at `concurrency.my`. D114's tutorial was to follow the ergonomics round, which is done.

- [ ] One example per feature (or one per group), with `#test` cases, registered in `test_examples_run.py` and `test_examples_compile.py`; the reading order extended
- [ ] Error-corpus files for the format-spec, slice, unit and `defer`-with-`await` errors the burn tests cover; `type_var_self_on_builtin.my` renamed for what it tests
- [ ] The tutorial and the "Why Myla" page (D114, [[MYLA-234]])
