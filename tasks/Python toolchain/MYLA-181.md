---
id: MYLA-181
title: One builtin table for the checker, the interpreter and the code generator; declared AST annotations
type: improvement
status: backlog
priority: medium
labels: [architecture, builtins]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). Every builtin is dispatched by name in three separate switch statements (`_infer_call` in [[src/myla/types.py]], 311 lines; `_eval_call` in [[src/myla/interpreter.py]]; `_gen_call` in [[src/myla/compiler/codegen_x86.py]]) plus `_BUILTIN_FUNCS`; adding `__getcwd` touched four Python files and the self-hosted compiler. The checker's annotations on AST nodes are dynamic attributes read with `getattr(node, "x", None)` at about 90 sites, so a missing one silently becomes `None`, which is how [[MYLA-174]] stayed hidden. Both matter before an LLVM backend ([[MYLA-160]]) adds a fourth consumer.

- [ ] A table `name → (signature check, interpreter, code generator)` or a `Builtin` enum, used by all three
- [ ] Every checker annotation declared on its dataclass with a default, the `getattr` idiom gone
- [ ] The same shape considered for [[selfhost/checker.my]], [[selfhost/interp.my]] and [[selfhost/lower.my]] (`eval_name_call` is an if-chain on names)

Waits for the decision in [[MYLA-201]].
