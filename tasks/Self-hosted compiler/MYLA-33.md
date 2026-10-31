---
id: MYLA-33
title: Latent issues in the self-hosted compiler
type: chore
status: done
priority: low
labels: [selfhost, codegen, checker]
---
Not reachable today, but each will bite:

- [x] `mono_token` maps every function type to `X`, so instantiations that differ only in a function-typed argument share a mangled name ([[selfhost/codegen.my]], around line 6079; compare [[MYLA-9]])
- [x] `checker.my` creates `Expr{id: 0}` (around line 3565), which collides with node 0 in the `resolved` table; harmless only while node 0 is a type expression
- [x] `is_builtin_call_name` (around line 5981) omits `__write_file` and `__run*`, so they're classified as indirect calls and get unused frame slots
- [x] `store_into_elem`'s aggregate drop walks through `%rcx`, which the called drop helpers clobber (around line 2336); `gen_assign` uses `%rbx` for exactly this reason
- [x] `gen_for_in_map` copies 8 bytes per key, wrong for aggregate keys (the checker only allows primitive keys today; known issue §2 in [[Archive/known_issues]])

## How

- `mono_token` gives function types a real token (`.F…R…`) instead of `X`: done with [[MYLA-9]], which also made the whole scheme injective.
- The checker's `struct_field_callee` built an `Expr{id: 0}` that overwrote node 0's type in `resolved`; `infer_method_call` now gets the real `target.field` callee node and types the function-valued field through it ([[selfhost/checker.my]]).
- `is_builtin_call_name` lists `__write_file` and the `__run*` primitives ([[selfhost/codegen.my]]).
- `store_into_elem` no longer exists: element stores go through `stage_value`/`commit_staged`, and `drop_stored` walks through callee-saved `%rbx` (fixed with [[MYLA-3]]/[[MYLA-4]]).
- `gen_for_in_map` copying 8 bytes per key is by design: the checker only allows scalar map keys, and the map slot layout (`[state:8][key:8][value]`) stores a key in one word in both backends. Allowing aggregate keys would change that layout everywhere.

## Evidence

The parity program of [[MYLA-9]] covers function-typed instantiations; the self-hosted gates and the bootstrap fixed point pass.
