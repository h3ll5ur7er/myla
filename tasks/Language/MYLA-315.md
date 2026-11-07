---
id: MYLA-315
title: "Generic constructors: an empty generic value, and a call's expected type in inference"
type: bug
status: review
priority: medium
labels: [checker, generics, inference]
---
Found by Advent of Code ([[Project/AoC-2015-2021]], F6). Generic types such as `Queue<T>` and `Heap<T>` can't have a constructor function, so each use spells out a literal. That blocks a clean standard library API ([[MYLA-314]]).

```myla fragment
struct B<T> { items: [T] }

fun mk<T>() -> B<T> {
    return B { items: [] }    // (1)
}

fun main() {
    let a: B<int> = mk()      // (2)
}
```

1. "cannot infer the element type of an empty list `[]`; annotate it (e.g. `: [int]`)". This is a bug. [[Language/Generics]] says the expected type (here the return type `B<T>`) seeds struct literals, and it does for a concrete `B<int>`, but not when the type argument is a type parameter: the field's expected type `[T]` should type the empty list.
2. "cannot infer type parameter(s) T for 'mk' from the arguments; add a type annotation to guide inference". This is documented: a call's type parameters are inferred from its arguments only, and Myla has no explicit type arguments on a call. A type parameter that no argument fixes should be taken from the expected type (`B<int>` here), as Swift and Rust do.

- [x] (1): the expected type seeds a struct literal's fields when its type arguments are type parameters; a test in the checker's cases and a program in every runner
- [x] (2): a call's expected type fixes the type parameters its arguments leave open, for generic functions and generic methods alike
- [ ] The owner's decision: whether explicit type arguments on a call (`mk<int>()`) come too (a revision of D34; see "Explicit type arguments" below)
- [x] [[Language/Generics]] updated

## Cause

Both are in [[selfhost/checker.my]].

1. `infer_type_args` (struct literals and variant constructors) gave a field no hint when its type, after the substitution, still named a type parameter. In `mk<T>` the expected `B<T>` maps the struct's `T` to the function's `T`, so `[T]` looked unsolved although the function's `T` is a known type in its body. The same test, `contains_type_param` after the substitution, decided the hints of `infer_generic_call` and `infer_generic_method`, so inside generic code an argument such as `[]` or a lambda got none either.
2. `infer_generic_call` and `infer_generic_method` were not given the call's expected type at all.

## What changed

- `solved_in(t, subst)`: whether the substitution solves every type parameter a signature's type names. Every one there is the callee's (or the struct's, the enum's) own, so this tells a known type from an open one where the substitution's values name the caller's type parameters.
- `arg_hint(pt, subst, lambda)`: one rule for the hint of a generic call's argument and of a generic literal's field: the type under the substitution when it solves it; for a lambda, a function type whose parameter types it solves, with the result left open ([[MYLA-356]], whose `lambda_param_hint` it replaces); else none. A generic literal's lambda field now gets the MYLA-356 hint too (`W { x: 3, f: (x) => x + 1 }`).
- `expected_subst(ret, expected)`: the call's declared result unified with its expected type, nothing when they don't fit (the expected type stays a hint; a wrong one is reported where the value is used, as before). `infer_generic_call` and `infer_generic_method` take `expected`: the arguments are solved first, left to right; an argument whose parameter's type they leave open is hinted with what the expected type adds (`subst_then`), so `let b: B<int64> = of([5000000000])` types the literal as an `int64`; then the expected type fills the type parameters the arguments left open, and every argument is verified as before.
- The native backend finds a generic call's instance from the arguments' types and now also from the call's own type (`solve_targs` in [[selfhost/codegen.my]], `call_target` in [[selfhost/lower.my]]); without that, a type parameter only the expected type fixed fell back to `int32`.
- The messages are unchanged: "cannot infer type parameter(s) T for 'mk' from the arguments; add a type annotation to guide inference" now means that neither the arguments nor an expected type fix `T`, and its advice (annotate) is what fixes it.

## Explicit type arguments (for the owner)

Not added: D34 decided that type arguments are written only in type positions, to dodge the ambiguity of `<`. In an expression `mk<int>()` parses today as `(mk < int) > ()`, and `a < b, c > (d)` in an argument list is two comparisons. What it would take:

- **Syntax.** Either a token that can't start a comparison, like Rust's turbofish `mk::<int>()`, which Myla's grammar has no other use for; or C#'s and Swift's rule: after a name, try to parse `<` as a type argument list, and keep it only if it closes with `>` and the next token is `(` (C# also accepts `)`, `]`, `.`, `,` and others). The parser ([[selfhost/parser.my]]) works on a token list with a resettable position (`self.pos = saved`, as `if … else` does), so the speculative parse fits, but its errors during the attempt must be dropped, and the grammar (`grammar/myla.ebnf`), the tree-sitter grammar generated from it and [[Language/Grammar]] change with it.
- **The AST and the checker.** A call node carries its type arguments; `infer_generic_call`/`infer_generic_method` start their substitution from them (a count mismatch is an error, like `expects 1 type argument(s), got 0`), which is the same seeding `expected_subst` does now. A method's explicit arguments would name only its own type parameters, not its impl's.
- **The backends** need nothing more: `solve_targs` already reads the instance off the checked types.
- **Is it needed?** With this task, every case that motivated it (`Set`, `Deque` and `Heap` constructors, [[MYLA-330]]) is written with an annotation, a parameter, a field or a return type, as in Swift, which has no explicit specialization of generic functions either. What still needs an annotation is a call whose result is used where nothing is expected: `let d = deque.new()`, a call statement, an argument of a generic call whose parameter's type is still open, `print(...)`.

## Evidence

- Test first. Before the change (the base 087e4fe's checker), the new programs fail with the two messages of this task: `generic_constructors_from_the_expected_type` with "cannot infer the element type of an empty list" (2) and "cannot infer type parameter(s) T for 'mk'" (5), `generic_arguments_hinted_by_the_expected_type` with "cannot infer the type of lambda parameter 'x'" (2), the three-module program the same way. After it, all check and run.
- `test_compiler_parity` (165 tests, OK): new `generic_constructors_from_the_expected_type` (pinned `0 1 0 4 q no top 0 b hihi 0 3 5000000000 5000000000 0 7`: a struct literal's `[]`, `[:]` and `None` in generic code; annotation, `var`, parameter, field, assignment to a field, return type, list element, `Some(…)`'s payload; `return mk()` in a generic function and in a generic method with its own type parameter), `generic_arguments_hinted_by_the_expected_type` (pinned `4 5000000000 s -1 12 200`), and `test_generic_constructors_of_a_module`, the shapes MYLA-330 needs across modules: `let d: Deque<int> = deque.new()`, `var s: Set<str> = set.new()`, `Graph { todo: deque.new(), seen: set.new() }`, `sizes(deque.new())`, `g.todo = deque.new()`, `let e: Deque<str> = d.emptied()`, `let big: Deque<int64> = deque.of([5000000000])`; interpreter and native code agree on all three. The native binary has one instance per type (`mk__4.i32`, `mk__4.str`, `mk__5.bool`, `mk__5.char`), and the same programs print the same on aarch64 (qemu).
- The checker's own cases, `build/myla test selfhost/checker.my`: 583/583, with new ones for `solved_in`, `all_solved_in`, `arg_hint`, `expected_subst`, `subst_then`, `is_lambda`, an `infer_type_args` case (`[]` against `[T]` with the expected type's `T` the function's) and `errors_of`, which checks seven whole programs: four of this task's shapes, an `int64` literal hinted by the expected type, and the two errors below.
- What stays an error, in `examples/errors/` with pinned diagnostics: `type_generic_call_nothing_fixes` (`let b = mk()`), `type_generic_call_param_not_in_result` (`fun count<T>() -> int` under `let n: int = count()`), `type_generic_method_nothing_fixes` (a call statement `b.emptied()`), and `type_generic_call_arguments_before_expected` (`let b: B<int> = of(["x"])`: the argument fixes `T = str` first, so the annotation is wrong, "cannot assign value of type 'B<str>' to binding of type 'B<int32>'"), and `type_generic_call_expected_breaks_bound` (a type parameter the expected type fixes is held to its bounds: `let h: Heap<P> = new_heap()` with `new_heap<T: Ord>`). `test_error_corpus`: 252 tests, OK.
- `test_selfhost_checker`, `test_std_modules`, `test_implicit_imports`: OK. `scripts/test.sh fast`: 630 tests, OK (1 skipped).
- `scripts/bootstrap.sh`: byte-identical fixed point (10,993,448 bytes). No new seed here: the pull request's last commit runs `scripts/update-seed.sh` (D156).
