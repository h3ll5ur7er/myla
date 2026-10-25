---
id: MYLA-38
title: Rust interpreter ignores names in struct and enum handling
type: bug
status: done
priority: medium
labels: [rust, interpreter]
---
Confirmed by running:

- [ ] Struct equality is positional and struct literals keep the order they were written in, so `P{x:1,y:2} == P{y:2,x:1}` is `false` and `P{x:1,y:2} == P{y:1,x:2}` is `true` (`value.rs`, `interp.rs`)
- [ ] Struct literals aren't checked against a declaration: `Nope { z: 5 }` evaluates although `Nope` doesn't exist
- [ ] Struct patterns ignore the struct name (`Q { x }` matches a `P`); there is a dead empty `if` where the check belongs
- [ ] Variant patterns compare only the variant name, so `B.Red` matches `A.Red()`
- [ ] `variant_to_enum` is one global map of unqualified variant names; collisions overwrite silently, and duplicate enum names aren't detected (`myla-sema/src/lib.rs`)
- [ ] A qualified nullary variant `Color.Red` without parentheses fails with "unknown name `Color`"

**Closed without a fix:** the Rust edition was removed from the repository ([[MYLA-70]]); its code is in git history (commit `043acb9`). See [[Architecture/Rust-edition]].
