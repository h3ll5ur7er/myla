# Monomorphization

The native backend never sees a type parameter (D13). The code generator ([[selfhost/codegen.my]]) makes the concrete copies of generic functions and types as it goes, under a substitution of the type parameters; the interpreter runs the generic program as it is, by erasure.

[TOC]

## What it does

1. **A worklist of functions**, starting from the entry point (`generate`): a function (methods included: they are functions named `Type.method`) is queued once an emitted function calls it, makes it a value or applies it partially ([[MYLA-108]]; `request_fn`, once per name: `fn_seen`). A generic one is queued per instantiation (`MonoFn`: the original name, its mangled name, the substitution of its type parameters), and its body is emitted with that substitution active. A call's instantiation comes from its declared parameter types unified with its arguments' types, then its result type with the call's own, for what only the call's expected type fixed (`solve_targs`, [[MYLA-315]]: `let d: Deque<int> = deque.new()`), and last a type parameter only a bound names, `T` of `I: Iterator<T>`, from the impl of `Iterator` that the instance's `I` has (D55, D171: the checker's `impl_args`, `impl_trait_args`). A trait's function without `self` called on a type parameter, `T.zero()` (D172), is the function of the type the instance substitutes for `T` (the checker's `static_calls`, by the call's id), and a generic impl's one has its impl's type parameters from that type (`static_selfs`: the impl's target).
2. **Types under the substitution.** The type of a node is the checker's (`resolved`) with the active substitution applied (`subst_type`), so layouts, calls and the per-type helpers are computed for concrete types. A generic struct, enum or actor used with concrete arguments gets the mangled name `Name__T1_T2`; an actor's handle (`Type.TActor(name, args)`) gets its cell's layout, drop and per-instance methods (`Cell.get__4.i32`) from the struct it is declared like, under its arguments ([[MYLA-386]]).
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

## Polymorphic recursion

A generic function that calls itself with a larger type, `grow<T>` calling `grow<[T]>`, asks for a new instance at each step, so the worklist never empties: `myla build` ran until it ran out of memory, where `myla check` says `ok` and the interpreter, which erases types, runs it ([[MYLA-415]], H5). The lowering refuses such a call where it is made (`call_target`): when an instance's type arguments are more than 64 types deep (`MAX_INSTANCE_DEPTH`, `type_depth`), or have more than 4,096 parts in all (`MAX_INSTANCE_SIZE`, `type_size`: a pair of pairs of … doubles at each step and is too large long before it is too deep), the call is a type error, as a refused `become` is ([[MYLA-272]]):

```
type error: the instances of 'grow' nest without end: this call asks for one whose type arguments are 65 types deep (the limit is 64)
  --> grow.my:3:16
note: 'grow' is called with a larger type at each step (polymorphic recursion), which native code can't be built for; the interpreter runs it
```

The program is refused once its first function asks for such an instance, after 64 instances at most; no program that terminates needs one, as the instantiations don't depend on the values. Through a lambda or a method the same holds; a recursion through a generic type alone (`enum Nest<T> { Leaf(T), Node(Nest<[T]>) }`, with a function walking it) is refused at the function's call.
