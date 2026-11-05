---
id: MYLA-185
title: Frame layout constants in one place, a typed table of runtime helpers, no __new suffix sniffing
type: improvement
status: backlog
priority: medium
labels: [selfhost, cleanup, backend]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). Three things the review found in the self-hosted backend that will bite the next change to frames or the runtime:

- the frame layout lives in three places that must agree: `FRAME_*` in [[selfhost/lower.my]], `FRAME_HEADER` in [[selfhost/ir_x86.my]] and literal offsets (`24(%rax)`, `32(%rdx)`, `48(%rdi)`, `64(%rdi)`) throughout `emit_executor` in [[selfhost/codegen.my]];
- runtime calls are strings (`Rt(d, "__str_concat", …)`, runtime entry points called as user functions with `Call(-1, "__wait", …)`), and the async `__new` convention is detected by comparing the last five characters of a name (`codegen.my`, `take_ir`);
- the syscall numbers and flag constants in `emit_executor` and `__start_workers` (202, 128, 129, 855808, 147490) have no names.

- [ ] One shared frame-layout record; named constants; a flag on the call site instead of the suffix
- [ ] `codegen.my` split by role (runtime text, layout, DWARF, census), or at least its sections named for what they hold

Decided by D108 ([[MYLA-217]]): one frame-layout record shared by the code generator's parts and later the other backends (D117), and one visitor for the four AST walks that collect names, now; the runtime leaves `codegen.my` with [[MYLA-162]]; the Python backend is frozen (D101), so only the self-hosted side.

- [ ] One visitor for the name-collecting AST walks (D108)

## Where things stand (2026-11-04, [[Project/Reflection-2026-11]])

The locations above moved, and the problem grew with two more backends:
- `FRAME_HEADER`, `slots_at` and `frame_size` are in [[selfhost/ir_x86.my]], and [[selfhost/ir_a64.my]] and [[selfhost/ir_wasm.my]] import them from there; `FRAME_*` is still in [[selfhost/lower.my]].
- The executor is written three times: `emit_executor` in [[selfhost/runtime_x86.my]], `emit_executor_a64` in [[selfhost/runtime_a64.my]], `emit_executor_wasm` in [[selfhost/runtime_wasm.my]], each with its own literal offsets; the unnamed `147490` (the `mmap` flags of a worker's stack) is in both native runtimes.
- The list and map headers (`16 + i * stride`), 8-byte words and 16-byte function values (D49) are numbers in the code of all three backends.
- The `__new` suffix check is gone; `__new` is reached by name (`myla_<f>__new`) from the function-value code, which [[MYLA-263]] replaces with IR.

So the first item becomes a layout module beside [[selfhost/ir.my]], target-neutral and used by the lowering and every backend, taking the word and pointer size from the target description ([[MYLA-262]], D122). That is a step before the next target, so its priority goes up.

- [ ] A layout module: the frame header and slots, list, map and builder headers, function values, environments; named constants for the platform flags; every backend using it
