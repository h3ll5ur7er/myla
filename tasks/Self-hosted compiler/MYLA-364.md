---
id: MYLA-364
title: "A derived Eq is lost when two derived types of different modules share a line and column"
type: bug
status: done
priority: high
labels: [checker, derive, modules]
---
Found by the `std.num` lane ([[MYLA-331]]). `Checker.synthesize_derives` in [[selfhost/checker.my]] skips a type when a derive already collected has the same line and column (`if d.line == decl.line && d.col == decl.col { present = true }`). So a derived type in one module is dropped when a derived type of another module sits at the same position, and every `==` on it fails: "operator '==' is not defined for 'dup$E'". `std.num` has the first `#derive` of `lib/std` (`ParseIntError`, line 782, column 1). So a user's derived type at 782:1, in any program that loads `std.num` (also through `std.fmt` or `std.json`), loses its `Eq`. `myla test lib/std/num.my --native` without `--stdlib` hits it too: the harness holds a copy of `std.num` and loads the embedded one.

Two modules, each with `#derive(Eq) pub enum E { A, B }` at the same line, and `e == E.A` in each.

- [x] Compare the declarations' ids, not their positions (`d.id == decl.id`)
- [x] A burn test: two modules with derived types at the same position, interpreted and native

## Evidence

Fixed in [[MYLA-313]]'s branch, where `synthesize_derives` gains `#derive(Hash)`: the derives collected are told apart by their declaration's id (`d.id == decl.id`), so `#derive(Hash)` shares the fix.

- Before: the reproduction (`dup.my` and `main.my`, each `#derive(Eq) pub enum E` at line 2) fails with `type error: operator '==' is not defined for 'dup$E'` under the base commit's `build/myla run`.
- After: `tests/burn/test_modules.py` `TestDerivesAtTheSamePlace` prints `false`, `true` interpreted and natively; the bootstrap keeps its byte-identical fixed point.

## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]].
