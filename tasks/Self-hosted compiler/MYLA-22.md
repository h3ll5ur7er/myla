---
id: MYLA-22
title: Self-hosted runtime never frees memory
type: bug
status: todo
priority: high
labels: [selfhost, runtime, memory]
---
`__free` starts with `ret`, so the size-class free-list code after it is dead ([[selfhost/codegen.my#L3972-L3975]]). It was disabled in "self-hosting part 5" (83cd293), probably to get past a use-after-free during bring-up.

Consequences:

- Every reference count and copy-on-write is bookkeeping only; memory is never reused. Compiling the compiler peaks at 361 MB; the 4 GiB arena runs out silently (`__trap`).
- It hides real reference-counting bugs: closure captures are stored without a retain (`store_capture`), `__func_drop` doesn't drop captures, and `__list_clone` is shallow. Turning `__free` back on will probably expose use-after-free bugs.

## Done when

- [ ] Find what broke when `free` was live (run the bootstrap with `ret` removed, under a debug arena that poisons freed cells)
- [ ] Fix capture retain/drop and the other unsound paths, matching the Python backend's ownership rules ([[Architecture/Native-backend]])
- [ ] Remove the `ret`; the fixpoint still holds; peak memory of a self-compile drops
- [ ] Port the arena-reclaim stress tests to the self-hosted backend
