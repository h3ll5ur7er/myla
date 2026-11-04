---
id: MYLA-181
title: "One builtin table for the self-hosted checker, interpreter and lowering"
type: improvement
status: backlog
priority: medium
labels: [architecture, builtins]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). Every builtin is dispatched by name in three separate switch statements (`_infer_call` in [[src/myla/types.py]], 311 lines; `_eval_call` in [[src/myla/interpreter.py]]; `_gen_call` in [[src/myla/compiler/codegen_x86.py]]) plus `_BUILTIN_FUNCS`; adding `__getcwd` touched four Python files and the self-hosted compiler. The checker's annotations on AST nodes are dynamic attributes read with `getattr(node, "x", None)` at about 90 sites, so a missing one silently becomes `None`, which is how [[MYLA-174]] stayed hidden. Both matter before an LLVM backend ([[MYLA-160]]) adds a fourth consumer.

- [ ] A table `name → (signature check, interpreter, code generator)` or a `Builtin` enum, used by all three
- [ ] Every checker annotation declared on its dataclass with a default, the `getattr` idiom gone
- [ ] The same shape considered for [[selfhost/checker.my]], [[selfhost/interp.my]] and [[selfhost/lower.my]] (`eval_name_call` is an if-chain on names)

D101 ([[MYLA-201]]) freezes the Python toolchain and removes it ([[MYLA-219]]), so the first two items are moot; what is left is the third, for the self-hosted checker, interpreter and lowering, before new backends ([[MYLA-62]]).

## Where things stand (2026-11-04)

What is left is the self-hosted side. A builtin is still added in three if-chains on its name: [[selfhost/checker.my]], [[selfhost/interp.my]] (`eval_name_call`) and [[selfhost/lower.my]]. Two more consumers came with the backends: each one recognises the lowering's runtime operations by name (`Inst.Rt`, 19 names), and [[MYLA-264]] turns those into a typed intrinsic. One table for the builtins — name, signature, interpreter, lowering to an intrinsic or a call — fits beside that.

- [ ] A builtin table (or a `Builtin` enum) used by the self-hosted checker, interpreter and lowering, the lowering producing [[MYLA-264]]'s typed intrinsics
