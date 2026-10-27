# Monomorphization

The native backend never sees a type parameter (D13). [[src/myla/compiler/monomorphize.py]] turns the checked program into a fully concrete one, then checks that again; the interpreter keeps running the original program by erasure.

[TOC]

## What it does

1. **Keep non-generic types.** Non-generic structs and enums are copied with their field and payload types rewritten concretely (aliases resolved, generic members replaced by their stamped names). `#derive` attributes are dropped, because the derived `impl` already exists as a function. Constants are copied.
2. **Specialise functions.** Every non-generic function (methods included: they are functions named `Type.method`) starts on a worklist. Specialising a function deep-copies it and rewrites it:
   - calls to generic functions become calls to `name__T1_T2` (from the checker's `Call.type_args`), which queues that instantiation;
   - method calls become plain calls `Type.method(recv, args…)`, so code generation needs no method support;
   - operators on a bounded type parameter that is now a struct or enum become trait-method calls;
   - enum constructors, struct literals, patterns and type annotations are renamed to the concrete stamped names.
3. **Stamp types.** Every generic struct/enum instantiation reached gets a copy named `Name__T1_T2` with its parameters substituted (stamping may reach further types).
4. **Check again.** The concrete program is checked with `check(program, with_prelude=False)`: the prelude's generic templates are gone and its instantiations are stamped.

Generic templates, type aliases, `impl` and `trait` declarations don't appear in the output; everything is plain functions and concrete types.

## Name mangling

`name__` followed by one token per type argument, each prefixed with its length, so the name reads back one way ([[MYLA-9]]):

- a user struct or enum: its name (a generic one: its own mangled name, so `Box<Pair<int, str>>` nests);
- a built-in type: `.` and its name (`.int32`, `.str`); identifiers can't contain `.`, so these never collide with user names;
- a tuple: `.T` and its elements' tokens; a list: `.L` and its element's; a map: `.M`, key, value; a function type: `.F`, its parameters, `R`, its return type (`.void` for none).

So `Pair<A_B, C>` is `Pair__3A_B1C`, `Pair<A, B_C>` is `Pair__1A3B_C`, and `first<int, (int) -> int>` is `first__6.int3215.F7.int32R7.int32`. The code generator names its per-type helpers (`__drop_list_…`, `__drop_map_…`) with the same tokens (`type_token`); the self-hosted code generator uses the same scheme with its own spellings (`.i32`, `.f64`).

## Cost

No dead-code elimination: every non-generic function is emitted whether it is called or not.
