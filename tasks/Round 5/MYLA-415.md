---
id: MYLA-415
title: "P2 Lowering and native runtime copies"
type: bug
status: todo
priority: high
labels: [lowering, runtime, memory-safety, round-5]
---
Work package P2 of [[Project/Review-2026-11-09]] (wave A1), with round 4's additions from [[Project/Review-2026-11-10]]. Files: `selfhost/lower.my`, `selfhost/codegen*.my` where needed, the deep-copy and drop routines of `lib/std/rt.my` (P5 owns its notifier and timer section, in wave A2). Reopens [[MYLA-313]] and [[MYLA-367]]'s native half.

- [ ] H2: an actor method that stores a list, map or string argument (`deep_param` passes a loaded slot as an address)
- [ ] H3: `__deepb_` of a shared recursive enum handed to a child task, and a child returning one
- [ ] H4: evaluate the key, index and argument before making the container unique: `m.remove(k())`, `m[k()] = v`, `xs[f()] = v`, `sb.append(…)`; audit every `Inst.Cow` site
- [ ] M3: no same-cell shortcut for `==` on lists unless the element's `==` is built in and reflexive (NaN, a user `eq`)
- [ ] M2, the native half: `method_instance` for the arithmetic traits (`impl<T: Add> Add for Box<T>` links)
- [ ] M15: values nested through closures release within a bounded stack (wasm32 at 3,000 levels, aarch64 at 30,000); the deep copy between tasks doesn't recurse
- [ ] H5: an instantiation depth limit for polymorphic recursion, a compile error instead of a build that never ends
- [ ] D183: native runtime errors carry the interpreter's texts with their values (`map key 5 not found`, the index and length)
- [ ] Z3 (with [[MYLA-416]]'s marker): `CodeGen.sig_of`'s fallback on `funcs[0]` goes; a file without `main` is a clean error for `myla build`; compiling an unread body is an internal error
- [ ] [[MYLA-384]]'s follow-up: the build hang of P2 (covered by H5)
- [ ] Tests: key and index expressions with side effects on their container; actors storing every heap type; recursive enums across tasks; on x86-64 and aarch64
