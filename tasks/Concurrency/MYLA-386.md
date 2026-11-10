---
id: MYLA-386
title: "Generic actors: actor Channel<T>"
type: feature
status: done
priority: medium
labels: [language, concurrency, actors, generics]
---
Found by the channels lane ([[MYLA-351]]): `actor Box<T>` is refused ("an actor can't have type parameters"), so `std.task`'s `Channel<T>` can't own its queue. The lane's version makes every program declare an actor per element type and pass its method in as a closure. A first-class `task.channel<int>(4)` needs generic actors.

- [x] `actor A<T> { … }` and `impl<T> A<T> { … }`: the checker, the interpreter, the lowering (an actor's instance per type argument), every target
- [x] Values crossing into and out of a generic actor are deep-copied as for any actor (D89–D97)
- [x] Parity programs and the concurrency stress tests over a generic actor

## Evidence

- **What it is.** An actor's handle type is `Type.TActor(name, args)` now, with its type arguments, where it was `TActor(name)`. Everything that handles a generic struct's arguments handles an actor's the same way: the checker's `type_name`, `type_eq`, `has_error`, `solved_in`, `contains_type_param`, `mentions_param`, `subst_type`, `subst_self`, `unify_param`, `struct_args_hint`, `check_keys_in` and `check_impl_target`; `struct_view` keeps the arguments, so `self.value` of a `Cell<int>` is an `int32`; `resolve_ref` and `infer_struct_lit` make `TActor(name, args)`. "an actor can't have type parameters" is gone. Natively `type_args_of`, `parts_of`, `mono_token` and the actor cell's drop take the arguments, and `actor_record_offset` sizes the cell from the fields under them (`actor_fields`, [[selfhost/lower.my]]). The monomorphizer already queued a method per receiver type, so each instance gets its own methods, drops and deep copies (`Cell.get__4.i32`, `Cell.get__4.str`, `__dropb_Cell__7.L4.i32`, …), on x86-64, aarch64 and wasm32. The interpreter runs one body for every instance, by erasure, and needed nothing but the new variant's shape.
- **Semantics** ([[Language/Concurrency#Generic actors]]):
  - `actor Cell<T> { … }` with `impl<T> Cell<T>`, its methods sync or async. Bounds go on an impl (`impl<T: Add> Cell<T>`), as for a struct, whose declaration takes none.
  - `Cell { value: 0 }` infers `T` from the fields or the expected type. Code names the type with its arguments, also in generic code: `fun make<T>(v: T) -> Cell<T>`, `struct Named<T> { slot: Cell<T> }`, `[Cell<T>]`.
  - An impl covers every instance (`impl Cell<int>` is an error). A bounded impl's method needs an instance that meets the bound.
  - Isolation, awaited calls, one call at a time per instance, deep copies in and out, and the D95 warning work as for every actor.
  - No rule limits the type arguments, since every value is sendable; `Cell<Cell<int>>` and `actor Node<T> { next: Option<Node<T>> }` work.
- **Tests first.** The seed compiler (b977e50's) rejects every new program: `type error: an actor can't have type parameters`, then `type 'Cell' is not generic (it takes no type arguments)`.
- **Parity programs** in `tests/burn/test_compiler_parity.py`, all six pinned:
  - `generic_actor_cell`: `Cell<T>` with `int`, `str`, `[int]` and `float64` from several tasks, and a bounded impl.
  - `generic_actor_queue`: async methods that await another actor, `task.yield()` and another instance of the same type.
  - `generic_actor_of_structs`: a list of structs, `Index<K, V>` with a map and a `[Box<V>]`, deep copies in and out.
  - `generic_actor_in_generic_code`: passed to and returned from generic functions, held in a generic struct's field and in a list, `Slot<Slot<int>>`.
  - `generic_actor_bounds_and_children`: `T.zero()` under `T: Zero + Add`, a method `mapped<U>`, children of an async method, `task.all`.
  - `generic_actors_nested`: an actor holding another of its type argument, and one linking to others of its own type.

  All six pass interpreted and natively, and also under `MYLA_TEST_TARGET=aarch64-linux` (qemu) and `wasm32-wasi` (node): 6/6 on each target.
- **Stress test.** `tests/burn/concurrency_stress/t30_generic_actor_from_many_tasks.my`: 32 tasks call a `Tally<int>` and a `Tally<[str]>` 208,000 times in all. A list sent in is changed after the call, and the actor keeps its copy. `test_concurrency_stress` passes (4 tests): the interpreter, native code on 1, 4 and 16 workers (3 runs each), and the `fifo` and `seed:1..3` orders in both. It also passes by hand on aarch64 with 4 and 16 workers, and on wasm32.
- **Checker.**
  - New `#test` cases in [[selfhost/checker.my]], [[selfhost/codegen.my]] and [[selfhost/lower.my]]: 691/691, 343/343 and 115/115.
  - `test_selfhost_checker.test_warnings_in_generic_actors`: D95 in a generic actor gives the same warnings as the same actor over `int`. That covers a check through `self.has()`, a change through `self.take() -> T` inside `Some(…)`, a list of `T`s set from a stale read, and quiet after a re-check.
- **Error corpus.** `type_actor_type_params.my` is removed (the program is valid now). Seven new files, each with its pinned `.stderr`: `type_generic_actor_concrete_impl`, `_uninferred`, `_unmet_bound`, `_field_from_outside`, `_type_args`, `_mismatch` and `_field_types`. The last one's message names the actor: `actor 'Pair': expected 'int32', found 'str'`.
- **Not changed.** The grammar (`struct_decl` already took `( "struct" | "actor" ) IDENT type_params?`) and the language server, whose tests pass.
- **Wiki.** [[Language/Concurrency]] has a new section, Generic actors, with a tested example, and the restriction is gone. [[Language/Generics]] and [[Architecture/Monomorphization]] are updated, and so is the `myla` skill (both copies).
- **Suites.** These all pass:
  - `scripts/test.sh fast`: 695 tests, 2 skipped.
  - `test_compiler_parity`, `test_selfhost_cases`, `test_error_corpus`, `test_selfhost_checker`, `test_grammar` and `test_lsp`, with tree-sitter: 670 tests.
  - `test_concurrency_stress`: 4 tests.
  - `test_doc_blocks`: 3 tests.

  The bootstrap reaches its byte-identical fixed point (17,092,271 bytes). The seed is left for the integrator (D156).
- **Found on the way.** This is not about generics. D95 doesn't count a `pop` inside an expression as a change: `let x = self.items.pop()` or `return Some(self.items.pop())` after an `await`, with `self.items` checked before it, gets no warning. A `self.items.pop()` statement does get one.

## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]], with a follow-up in [[MYLA-415]]: its probes found the actor segfault (H2).
