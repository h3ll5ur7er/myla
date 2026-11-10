---
id: MYLA-384
title: "Trait functions without self: T.f(x) on a type or a type parameter"
type: feature
status: done
priority: medium
labels: [language, traits, generics, checker]
---
The language part of D172 ([[MYLA-354]]). Its own pull request, with its seed (D156). [[MYLA-385]] (`#derive(Json)`) builds on it.

```myla fragment
trait Zero {
    fun zero() -> Self
}

impl Zero for int {
    fun zero() -> int { return 0 }
}

struct Money {
    cents: int64,
}

impl Zero for Money {
    fun zero() -> Money { return Money { cents: 0 } }
}

fun total<T: Zero + Add>(xs: [T]) -> T {
    var s = T.zero()
    for x in xs { s = s + x }
    return s
}
```

- [x] A trait declares, and its impls define, functions without a receiver; `Self` in their signatures is the implementing type
- [x] `Type.f(args)` on a type that implements the trait (a struct, an enum, a built-in type: `int.zero()`), and `T.f(args)` on a type parameter bounded by it; the call resolves statically (D55: one impl per type), in the checker, the interpreter and the lowering on every target, generic instances included
- [x] Only trait functions: an inherent `impl P { fun f() }` without `self` stays an error (no static methods outside traits), unless the task finds a reason to allow it — say so if so
- [x] What a name means: `T.f` where `T` is a type parameter, `P.f` where `P` is a type, `m.f` a module's function (D170's `m.T` in types); a clash (a type and a module of one name) has a clear message
- [x] The grammar, tree-sitter, the language server (hover, definition), the wiki ([[Language/Methods-and-traits]], [[Language/Generics]]), the `myla` skill
- [x] Parity programs on every target, the error corpus (a function without `self` called on a value, on a type that doesn't implement the trait, an unbounded type parameter, an inherent one)

## Evidence

Built on `91901f8` (D172). Tests written first: the base compiler rejects every new program at the parser (`a method's first parameter must be 'self' or 'var self'` for `fun zero() -> Self`, `expected an expression, found 'int64'` for `int64.zero()`).

**Syntax** (`grammar/myla.ebnf`, [[Language/Grammar]], tree-sitter regenerated):

- `method_head` takes `method_params = ( receiver | param ) …`: a method may have no receiver, in a trait and in an impl ([[selfhost/parser.my]], `method_header`). The checker allows it in a trait and its impls only.
- A type keyword before `.` is a name in an expression, `int64.zero()` (`primary`: `prim_type "." member`); `int`, `float`, `char` are identifiers already.
- **Generic types:** a generic type's function is called on its name alone, `Box.zero()`, its type arguments from the arguments and the expected type, as a generic function's (`let b: Box<int> = Box.zero()`). `Box<int>.zero()` is not supported: it reads as a comparison, and the parser says what to write instead when a `<` after a name closes right before a `.` (`type_args_then`). A list or map type can't stand before `.`; a generic function names it (`make<[int]>()`). `Self.f()` inside an impl isn't supported either (name the type).

**Semantics** ([[selfhost/checker.my]]):

- A trait's function without `self` has receiver `""` and no `Self` parameter (`resolve_traits`); an impl's is registered as `Key.f` without a `self` parameter, its impl target kept in `static_selfs` (`register_method`). Conformance compares receivers both ways (`'a' in impl … has no receiver but the trait declares 'self'`, `… has receiver 'self' but the trait declares a function without 'self'`).
- **Inherent functions without `self` stay an error** (`inherent_function`): `function 'f' in 'impl P' has no 'self': only a trait's functions go without one`, with a help note. No strong reason to allow them was found: a module's free functions already read as constructors (`deque.new()`), and allowing them would add a second way to write every constructor. An enum's function can't take a variant's name.
- `X.f(args)` in `infer_call`: a local named `X` is a value (a method call); else `static_target` gives a type parameter in scope, a struct, enum (a generic one without arguments, solved like a generic call), a built-in type or an alias; `infer_static_call` checks the impl's function (generic impls through `infer_generic_call`), `bound_static_call` a type parameter's bound traits' functions with `Self` = the parameter. Each such call is recorded in `static_calls` (call id → the type it is called on, in the caller's type parameters). `m.f` and `m.T.f` are folded by the loader first ([[selfhost/loader.my]]; a type parameter is no longer renamed as a global or a module there); a module alias and a type of one name in one file is the loader's existing error (`import of 'money' collides with an existing name in this module — rename with 'as'`).
- The messages: `'zero' is a function of 'int32' without 'self': call it on the type, 'int32.zero(…)', not on a value`, `'zero' is a function of trait 'Zero' without 'self': call it on the type, 'T.zero(…)', not on a value`, `type 'str' has no function 'zero'` (help: `trait 'Zero' declares it: 'impl Zero for str' would give 'str' one`), `type parameter 'T' has no function 'zero': it has no bounds (write 'T: Trait' to call a trait's functions)`, `'area' is a method of 'Sq' (it takes 'self'): call it on a value, 'x.area(…)'`, `'int32.zero' names a type's function, not a value: …`. A `become` can't call a type's function (it isn't marked as a call for `become`).

**Running it:**

- Natively ([[selfhost/lower.my]] `call`, [[selfhost/codegen.my]] `solve_targs`): a static call is a direct call of `Key.f`, `Key` the type the instance substitutes for the recorded one, its arguments without a receiver; a generic impl's function has its impl's type parameters from that type (`static_selfs`). The scan of kept parameters and `ctor_info` don't take an enum's function for a variant. One IR, so x86-64, aarch64 and wasm32 alike.
- The interpreter ([[selfhost/interp.my]]) erases types, and `T.zero()` has no value to dispatch on, so when a program calls a trait function on a type parameter (the checker's `on_type_params`) a generic function's frame binds its type parameters (`%:T`, an index into the interned `types`): at each call, from the checker's solved type arguments of the call (`call_types`) in the caller's frame, or for a method or static call without them from the receiver's type unified with the impl's target (`env_of`, `bind_next`, `bind_types`); a `become` carries them (`env_tail`), lambdas capture them, async bodies keep them in their deferred frames. `eval_static_call` calls the function of the bound type; `recv_key` uses the bound type for a temporary of type `T` (`T.unit().area()`). Programs without such a call run as before.
- Language server ([[tools/lsp/resolve.my]]): `T.zero` resolves to the bound trait's declaration, `int.zero` and `Money.zero` to their impl's function, hover shows `fun zero() -> Self` and `type parameter T: Zero`.

Tests:

- `test_compiler_parity`: new `trait_functions_zero` (the task's example, `int64.zero()`), `trait_functions_default` (`Default` over a struct, an enum, `bool`, `int`, `str`, `char`; a generic impl `Box<T>` whose function calls `T.default()`; a generic method; `impl<T: Default> Default for [T]`; `make<[Box<char>]>()`; a lambda keeping its function's `T`), `trait_functions_parse` (a mini `FromJson`, `fun parse(text: str) -> Result<Self, ParseError>`, `?` through `Point` and `[T]`, `decode<[[int]]>`), `trait_functions_with_methods` (a trait with three functions and two methods, `T.unit().area()`, a generic struct's methods, a method's own `U.unit()`), `trait_functions_async` (across `await`, in an `async let` child, in a lambda of an async function, nested `Pair<Pair<str>>`), `trait_functions_become`, all `PINNED`, and `test_trait_functions_across_modules` (the trait in one module, impls in another, calls in a third: `Money.zero()`, `m.Money.zero()`, `int.label()`, `z.sum(…)`, `z.label_of<Wallet<Wallet<Money>>>()`, `m.Wallet.zero()`). With `MYLA_TEST_TARGET=aarch64-linux` and `wasm32-wasi` (`-k trait_functions`): 7/7 each, and the scratch programs built for both and run under qemu-aarch64 and `node tools/wasm/run.mjs` print what the interpreter prints.
- A new example, [[examples/trait_functions.my]], with `#test` cases (10/10 interpreted and `--native`), registered in both example suites.
- The error corpus, each pinned with its `.stderr`: [[examples/errors/type_trait_function_on_a_value.my]], [[examples/errors/type_trait_function_on_a_bounded_value.my]], [[examples/errors/type_trait_function_not_implemented.my]], [[examples/errors/type_trait_function_unbounded_type_parameter.my]], [[examples/errors/type_inherent_function_without_self.my]] (was `parse_method_no_self.my`: the inherent case is now the checker's), [[examples/errors/type_trait_method_on_a_type.my]], [[examples/errors/type_trait_function_receiver_mismatch.my]], [[examples/errors/type_trait_function_as_a_value.my]], [[examples/errors/type_trait_function_names_a_variant.my]], [[examples/errors/parse_generic_type_function.my]].
- The checker's cases: new ones for `static_target`, `infer_static_call`, `bound_static_call`, `static_hint`, `inherent_function`, `type_args_in`, and eleven `errors_of` programs; the parser's `type_args_then`, the interpreter's `env_type`, `env_of`, `tp_names_i`, the language server's `join_bounds`, `split_bounds`. `test_lsp`: `test_trait_functions_without_self`.
- `scripts/test.sh fast`: 676 tests, OK (1 skipped). `python3 -m unittest tests.burn.test_compiler_parity tests.burn.test_grammar tests.burn.test_lsp tests.burn.test_selfhost_cases tests.burn.test_error_corpus tests.burn.test_selfhost_checker` (with the tree-sitter CLI): 656 tests, OK; the error corpus alone 286. `test_examples_run`, `test_examples_compile`, `test_doc_blocks`: 79 tests, OK. `myla test`: `selfhost/checker.my` 672/672, `selfhost/parser.my` 170/170, `selfhost/interp.my` 375/375, `tools/lsp/resolve.my` 4/4.
- The bootstrap reaches its byte-identical fixed point (15,591,451 bytes). The compiler's own sources and the standard library use none of the new syntax, so the current seed builds them; `selfhost/embedded_std.my` is unchanged. No new seed here (D156: the pull request's last commit runs `scripts/update-seed.sh`).
- Found on the way, not fixed here (a task suggested): interpreted, a method call on a temporary whose type is a type parameter, `x.scaled(2).area()` with `x: T`, prints `ERR: VUnit` (native code is right) when the program calls no trait function on a type parameter; with one, the frame's binding covers it.

## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]], with a follow-up in [[MYLA-417]]: an impossible hint for `Box.tag()`; the build hang is [[MYLA-415]]'s.
