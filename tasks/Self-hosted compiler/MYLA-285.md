---
id: MYLA-285
title: Raw-memory primitives are callable from a program with a warning
type: bug
status: done
priority: high
labels: [checker, safety]
---
Found by the review of 6 November 2026 ([[Project/Review-2026-11]]). D100 made calling a `__` primitive from a program a warning, written for the I/O primitives. `__load64`, `__store64`, `__free`, `__addr_of`, `__copy_bytes`, `__call_code` and the other raw-memory primitives (`is_raw_memory_primitive` in [[selfhost/checker.my]]) are under the same warning: `print(__load64(0))` passes `check` and segfaults natively with no `runtime error` line (`__on_segv` reports only stack faults); `__free(__load64(__addr_of(s)))` frees a live string. The interpreter refuses them (`'__load64' reads and writes raw memory, which only native code does`). `build/myla build selfhost/main.my` prints 36 such warnings from `interp.my`, which implements them.

- [x] A call of a raw-memory primitive outside `std$` (and outside the self-hosted interpreter's own module, which implements them) is an error in the checker; the I/O primitives keep D100's warning
- [x] An error-corpus file; the 36 warnings from `interp.my` gone (the interpreter's uses allowed by its module, or the primitives reached another way)

## Done (2026-11-07)

- D152: a call of a raw-memory primitive (`is_raw_memory_primitive`) from a function that isn't the standard library's is the type error "'__load64' reads or writes raw memory: only the standard library may call it", with a help line; the I/O primitives keep D100's warning. `gen_main --primitives` lets a program call them, for the toolchain's tests of their code (`test_raw_memory`, `test_selfhost_codegen`'s `_emit_asm`); the `myla` CLI has no such flag.
- `examples/errors/type_raw_memory_call.my`; `test_raw_memory` now checks that `myla build` and `myla run` refuse its program with that message.
- Not done: the CLI's 38 warnings building `selfhost/main.my` are all I/O primitives (`__read_file`, `__run`, `__spawn`, …) that the interpreter implements for the programs it runs, none of them raw memory. Silencing them needs a way for a module to say it implements primitives (an attribute, or the toolchain's modules recognised), a language-surface choice left for the owner.

## Evidence (the last box, D161)

- Warnings have names, shown as `warning[primitive]: …` / `warning[reentrancy]: …` (`diag.warning_name`, the one map from a message to its name; `kind_shown` in rendering) and sent as the language server's diagnostic code. `#allow(name, …)` on a function, a method or an `impl` block silences them in its body (`check_body` sets `allowed`; an impl's `#allow`s go onto its methods when they are registered); `#allow(primitive(__a, __b))` silences those primitives only. `check_allow`: no names, a list on another name, a list of what isn't a primitive, and a raw-memory primitive (D152) are errors; an unknown name is a warning.
- `selfhost/interp.my`'s `impl Interp` carries `#allow(primitive)`: `myla check` of every file of `selfhost/` and `tools/` gives no warning now (the 36 were all in that impl).
- The grammar takes attributes before an `impl` (`grammar/myla.ebnf`, [[Language/Grammar]], tree-sitter regenerated); `ImplDecl` and `TraitDecl` carry their attributes, which the canonical dump shows only when there are some, so the recorded dumps are unchanged.
- `tests/burn/test_allow.py` (the name shown, on a function, on a list of primitives, on an impl, on a method, `reentrancy` on an actor's impl, an unknown name, six errors); error corpus `type_allow_raw_memory.my`, `type_allow_on_struct.my`; `type_main_on_method.my`'s message names `#allow` and is pinned in its `.stderr`. The recordings that predate D161 are adjusted where they meet it: the `myla check` warning's name in `test_selfhost_cli`, the editor's code in `_lsp_scenarios`, the page's count in `test_wasm`, `unit_test_164` in the checker gate's `SUPERSEDED`, and the parser snippet `#test` on an impl (now the checker's error) dropped.
- [[Language/Attributes-and-testing#warnings-and-allow]], [[Language/Concurrency]], [[Language/Standard-library]], D161.
