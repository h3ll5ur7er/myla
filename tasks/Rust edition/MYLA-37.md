---
id: MYLA-37
title: Rust native backend crashes and coverage gaps
type: improvement
status: done
priority: medium
labels: [rust, codegen]
---
## Crashes

- [ ] `var x = 0` then `x = 1.5` panics inside cranelift-frontend ("declared type of variable var0 doesn't match"): assignment doesn't convert or check types
- [ ] `print()` with no arguments indexes `args[0]` and panics

## Coverage

The backend lowers only non-generic, non-async functions over int/float/bool/str with `let`/`var`, arithmetic, comparisons, `if`, `while`, `for a..b`, direct calls and `print`.

- [ ] Every function is lowered, used or not, so one unsupported construct anywhere fails the whole build ("unknown function `len`"): lower only what `main` reaches
- [ ] Errors name no span or function ("native backend does not yet support this expression"): add both
- [ ] Output into a missing directory fails with a bare "No such file or directory"
- [ ] Next constructs to support: `break`/`continue`, structs, enums, strings beyond literals, lists
- [ ] Remove the dead `Codegen.strings`

**Closed without a fix:** the Rust edition was removed from the repository ([[MYLA-70]]); its code is in git history (commit `043acb9`). See [[Architecture/Rust-edition]].
