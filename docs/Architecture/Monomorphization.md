# Monomorphization

The native backend never sees a type parameter (D13). The code generator ([[selfhost/codegen.my]]) makes the concrete copies of generic functions and types as it goes, under a substitution of the type parameters; the interpreter runs the generic program as it is, by erasure.

[TOC]

## What it does

1. **A worklist of functions**, starting from the entry point (`generate`): a function (methods included: they are functions named `Type.method`) is queued once an emitted function calls it, makes it a value or applies it partially ([[MYLA-108]]; `request_fn`, once per name: `fn_seen`). A generic one is queued per instantiation (`MonoFn`: the original name, its mangled name, the substitution of its type parameters), and its body is emitted with that substitution active.
2. **Types under the substitution.** The type of a node is the checker's (`resolved`) with the active substitution applied (`subst_type`), so layouts, calls and the per-type helpers are computed for concrete types. A generic struct or enum used with concrete arguments gets the mangled name `Name__T1_T2`.
3. **Lambdas** are lifted into functions of their own per instantiation (`LamJob`, with the substitution of the function they are created in).
4. **Per-type helpers.** The concrete owning types met (lists, maps, boxed enums, …) queue their drop, clone and other helpers, one per mangled type.

Nothing is checked again: the checker checked the generic program once. Generic templates, type aliases, `impl` and `trait` declarations produce no code of their own.

The Python backend did this in a separate pass instead (`src/myla/compiler/monomorphize.py`, retired with it, [[MYLA-219]]): it copied the program with every generic function and type stamped out concretely, method calls turned into plain calls and operators on bounded type parameters into trait-method calls, and checked the concrete program again.

## Name mangling

`name__` followed by one token per type argument, each prefixed with its length, so the name reads back one way ([[MYLA-9]]; `mangle_fn`, `mono_token`):

- a user struct or enum: its name (a generic one: its own mangled name, so `Box<Pair<int, str>>` nests);
- a built-in type: `.` and its name (`.i32`, `.u8`, `.f64`, `.str`, `.char`, `.bool`, `.sb`); identifiers can't contain `.`, so these never collide with user names;
- a tuple: `.T` and its elements' tokens; a list: `.L` and its element's; a map: `.M`, key, value; a function type: `.F`, its parameters, `R`, its return type (`.void` for none).

So `Pair<A_B, C>` is `Pair__3A_B1C`, `Pair<A, B_C>` is `Pair__1A3B_C`, and `first<int, (int) -> int>` is `first__4.i3213.F4.i32R4.i32`. The per-type helpers (`__drop_list_…`, `__drop_map_…`) are named with the same tokens. (The Python backend spelled the built-in types out: `.int32`, `.float64`.)

## Cost

Only functions reachable from the entry point are emitted, each instantiation once. (The Python backend emitted every non-generic function, called or not.)
