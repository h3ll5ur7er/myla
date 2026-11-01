---
id: MYLA-185
title: Frame layout constants in one place, a typed table of runtime helpers, no __new suffix sniffing
type: improvement
status: backlog
priority: low
labels: [selfhost, cleanup]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). Three things the review found in the self-hosted backend that will bite the next change to frames or the runtime:

- the frame layout lives in three places that must agree: `FRAME_*` in [[selfhost/lower.my]], `FRAME_HEADER` in [[selfhost/ir_x86.my]] and literal offsets (`24(%rax)`, `32(%rdx)`, `48(%rdi)`, `64(%rdi)`) throughout `emit_executor` in [[selfhost/codegen.my]];
- runtime calls are strings (`Rt(d, "__str_concat", …)`, runtime entry points called as user functions with `Call(-1, "__wait", …)`), and the async `__new` convention is detected by comparing the last five characters of a name (`codegen.my`, `take_ir`);
- the syscall numbers and flag constants in `emit_executor` and `__start_workers` (202, 128, 129, 855808, 147490) have no names.

- [ ] One shared frame-layout record; named constants; a flag on the call site instead of the suffix
- [ ] `codegen.my` split by role (runtime text, layout, DWARF, census), or at least its sections named for what they hold

Waits for the decision in [[MYLA-201]] and [[MYLA-217]].
