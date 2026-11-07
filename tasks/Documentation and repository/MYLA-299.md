---
id: MYLA-299
title: Examples and doc blocks for the November features
type: chore
status: in-progress
priority: medium
labels: [docs, examples]
---
Found by the review of 6 November 2026 ([[Project/Review-2026-11]]). No file in `examples/` uses any of the sixteen features of the November round (`defer`, `if let`, `while let`, slices and `^`, format specs and `Format`, `+=`, `if` expressions, let-else, default parameters, the unit type, `std.math`, `std.time`, `task.sleep`/`timeout`/`yield`), and the reading order in [[Getting started]] ends at `concurrency.my`. D114's tutorial was to follow the ergonomics round, which is done.

- [x] One example per feature (or one per group), with `#test` cases, registered in `test_examples_run.py` and `test_examples_compile.py`; the reading order extended
- [x] Error-corpus files for the format-spec, slice, unit and `defer`-with-`await` errors the burn tests cover; `type_var_self_on_builtin.my` renamed for what it tests
- [ ] The tutorial and the "Why Myla" page (D114, [[MYLA-234]])

## Evidence (first two boxes)

- `examples/branches_and_defaults.my` (`if` as a value, `if let`, `while let`, let-else, `+=`, `defer`, default parameter values), `examples/slices_and_formats.my` (slices and `^`, a negative step, format specs, a type's own `Format`, the shortest float), `examples/time_and_math.my` (`std.time`, `task.sleep`, `task.timeout`, `task.yield`, `std.math`). Each function returning a value has `#test` cases (13 in all, passing); the three are in `test_examples_run.EXPECTED` and `test_examples_compile.EXAMPLES`, and print the same natively. [[Getting started]]'s reading order has them as step 7.
- Adding them showed two things: the oracle gates asked the recordings about every example, so a new one failed them (fixed under [[MYLA-288]] with `RECORDED_EXAMPLES`), and the language server gave a format spec in an f-string (`{rest:02}`) no semantic token: `fstring_spans` in [[tools/lsp/semantic.my]] now gives the spec, `:` to `}`, the string's token (the lexer's `spec_colon`, now public, says where it starts). The resolution test skips the lexer's own tokens, such as the `format` an f-string expands to, which first mattered in a file declaring a `format` method.
- Error corpus: `type_format_spec_kind.my`, `type_slice_of_a_map.my`, `type_slice_bound_not_int.my`, `type_defer_await.my`; the unit's (`type_unit_ordering.my`) was there, and `type_var_self_on_builtin.my` was renamed `type_async_var_self_on_builtin.my` with [[MYLA-221]].
- Open: the tutorial and the "Why Myla" page.
