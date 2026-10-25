---
id: MYLA-60
title: Code generator spends almost all of stage 1 collecting list types
type: improvement
status: todo
priority: high
labels: [native-backend, performance, bootstrap]
---
Building the self-hosted compiler with the Python toolchain (bootstrap stage 1) takes about 60 s, and about 98% of it is `_collect_list_types` ([[src/myla/compiler/codegen_x86.py#L250-L314]]). For every AST node it calls `_gather_list_types` on the node's type, which recursively walks every field of every struct and enum reachable from it, without remembering what it has already seen. The self-hosted compiler's big state structs are walked tens of thousands of times (85 million calls).

Loading, checking and monomorphizing take under 2 s; generating the functions themselves about 3 s.

**Measured (2026-10-25):** keeping one visited set of types for the whole collection (return at once for a type already gathered) brings stage 1 from **57 s to 3.8 s**. The generated compiler produces a byte-identical `stage2.s`.

## Done when

- [ ] `_gather_list_types` skips types it has already visited (types are hashable frozen dataclasses); the per-path `seen` set becomes unnecessary
- [ ] The emitted helper order stays deterministic
- [ ] `tests/burn` passes; the bootstrap fixed point holds
- [ ] Stage 1 time recorded on [[Development/Bootstrap]]
- [ ] Check [[selfhost/codegen.my]] for the same pattern (its stage 3 already takes 2 s, so probably not)
