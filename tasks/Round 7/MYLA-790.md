---
id: MYLA-790
title: "R7-1 Checker: operator impl bounds (H1), a program's own std/ (H2), async operator methods (H3), left literals"
type: bug
status: todo
priority: high
labels: [checker, round-7]
---
Work package of [[Project/Review-2026-11-17]], lane "Checker" (section 5). Files: `selfhost/checker.my`. The reproducers are in the review's bundle (`repro-r6/`, with a README per area); each fix turns its reproducer into a test that fails before it. The owner's decisions it builds: D255, D256 and D257. New tasks it files take ids 801–808.

- [ ] **H1** (high, new): an impl's bounds aren't checked where an operator with type arguments, `Neg`, `Index` or `IndexSet` picks it (`*`, `*=`, unary `-`, `x[i]`, `x[i] = v`, a `T: Mul<float>` argument; no `impl_bound_failing` after `find_op_impl`). With a parity program that meets the bounds. `repro-r6/checker/HIGH_op_impl_bound_unchecked_*.my`. Reopens [[MYLA-612]]; closes [[MYLA-538]]'s hole again
- [ ] **H2** (high, old): a program's own `std/process.my` with an empty `exit` makes a function without a `return` pass and segfaults natively; `exit` and `task.cancel` go by the `std$` name. `repro-r6/checker/own_std_process/`. Reopens [[MYLA-584]]. Decision 1
- [ ] **H3** (high, old): `impl Add for V { async fun add(…) }` is accepted and `v + v` calls it from plain code. `repro-r6/checker/op_async_method_called_by_operator.my`. File a task. Decision 2
- [ ] **M15**: `B { v: 1 } * b` takes the right operand's type for the left struct literal; and a literal on the left doesn't adapt (`2.0 * v` on a `vector32.Vec3`). `repro-r6/checker/op_left_struct_literal_takes_right_type.my`
- [ ] Messages: `mul$int32`, `set_index$int32`, `Mul<{error}, …>`; `g[0].a = 5` on an `Index` type says "not a list"; `#track_caller` twice is accepted
- [ ] [[MYLA-544]]/[[MYLA-609]]'s follow-up: literals inside `Some(…)`, tuples and lists on the left
- [ ] [[MYLA-394]]'s follow-up (D95): an `await` in the index of a plain index assignment, and a `defer` registered before the `await`
- [ ] Decision 3 as the owner took it, D257: any module may implement any trait for any type (no orphan rule); two impls of the same trait with the same type arguments for the same type are an error wherever they are, both named; the operators page states the literal rule
