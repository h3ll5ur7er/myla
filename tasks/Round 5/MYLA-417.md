---
id: MYLA-417
title: "P3b The checker: generic operators, literals, D178's call error, diagnostics"
type: bug
status: todo
priority: high
labels: [checker, diagnostics, round-5]
---
Work package P3 of [[Project/Review-2026-11-09]], the checker half that [[Project/Review-2026-11-10]] §5 splits off (wave A1). Files: `selfhost/checker.my`, the prelude's derives, the language server where a diagnostic changes. Reopens [[MYLA-367]]'s checker half and [[MYLA-394]].

- [ ] M2, the checker's half: `infer_overload_known` substitutes, so `Box<int> + Box<int>` is `Box<int>`, not `Box<T>`
- [ ] [[MYLA-394]]: D95 counts a mutator in the head of `if`, `while` and `match`
- [ ] M24: `()` as a type argument ("expected '() -> ()', found '() -> ()'"); unblocks `std.bench` on closures that return nothing ([[MYLA-426]])
- [ ] D178 (L1): where `x.f(…)` finds a method and the receiver's field `f` holds a function at that instantiation, the error `bind the field first: let g = x.f`
- [ ] L2: an integer literal before the element that fixes a literal's type is re-checked against it (`[1, 300, 3u8]`, map keys too)
- [ ] L5: `let w: uint8 = -1` is an error
- [ ] L6: [[MYLA-401]]'s unfilled hole reported at the hole; [[MYLA-398]]'s `'shapes.Area' is a trait of module 'shapes', not a trait` and the bare name of an unsatisfied `T: b.Show`
- [ ] [[MYLA-401]]'s quadratic join (64,000 `None`s then a `Some`: 40 s)
- [ ] D182: `Option` and `Result` derive `Hash`
- [ ] [[MYLA-379]]'s follow-up: `Tree.Leaf == t` types as `t == Tree.Leaf` does
- [ ] [[MYLA-356]]'s follow-up: `r.and_then((x) => Ok(x + 1))` infers `E` from the receiver
- [ ] [[MYLA-315]]'s follow-up: the expected type passes through `?`; no "add a type annotation" where the annotation is the problem
- [ ] [[MYLA-380]]'s follow-up: an enum can be a stateful iterator
- [ ] Diagnostics of §3.3: `'__list'`/`'__map'` and `__list.sorted` in messages ([[MYLA-320]], [[MYLA-383]]), `unmangled` on finished message text, "a enum … not a type", a hint towards `m.items()` for `for (k, v) in m` ([[MYLA-390]]), [[MYLA-371]]'s three misleading diagnostics, [[MYLA-384]]'s impossible hint for `Box.tag()`
- [ ] [[MYLA-398]]'s language-server gaps
