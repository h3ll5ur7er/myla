---
id: MYLA-380
title: "Iterators in the language: the Iterator trait, generic-trait bounds, for over an iterator"
type: feature
status: review
priority: medium
labels: [language, checker, generics, traits, iterators]
---
The compiler part of D171 ([[MYLA-353]]). Its own pull request, with its seed (D156). [[MYLA-381]] (`std.iter`) builds on it.

```myla fragment
struct Countdown {
    n: int,
}

impl Iterator<int> for Countdown {
    fun next(var self) -> Option<int> {
        if self.n == 0 { return None }
        self.n -= 1
        return Some(self.n + 1)
    }
}

fun total<I: Iterator<int>>(it: I) -> int {
    var s = 0
    for x in it { s += x }
    return s
}
```

- [x] `trait Iterator<T> { fun next(var self) -> Option<T> }` in the prelude
- [x] A bound names a generic trait with its arguments, `I: Iterator<T>`, in a function's, a method's and an impl's type parameters: the grammar (`grammar/myla.ebnf`, tree-sitter), the parser, the checker (the bound checked at the call against the type's one impl, D55; inside the body the trait's methods with `T` substituted)
- [x] `for x in e` over a type implementing `Iterator<T>`: `var it = e; while let Some(x) = it.next() { … }`, in the checker, the interpreter (sync and async loops) and the lowering; `break` and `continue` work; lists, maps, strings and ranges are unchanged
- [x] Parity programs, interpreted and native on every target: a user iterator, a generic adapter struct with a bounded impl (`impl<I: Iterator<T>, T, U> Iterator<U> for Map<I, T, U>`), `for` over both, a copied iterator keeping its own position
- [x] The error corpus: a bound not satisfied, a wrong argument count on a bounded generic trait, `for` over a type that implements no `Iterator`
- [x] [[Language/Methods-and-traits]], [[Language/Generics]], [[Language/Statements]] (loops), [[Language/Grammar]], the `myla` skill
- [x] Measured: the lazy `Range → Map → Filter` sum of [[MYLA-353]] natively and interpreted, against the hand-written loop

## Evidence

Built on `5b34e9c` (the tip of wave 3, PR #47). Tests written first: the three parity programs failed to parse ("expected '>' to close type parameters, found '<'") and to check ("`for ... in` requires a list or map, found 'Upto'", "unknown trait 'Iterator'").

**How it is built.** The checker does the work; the interpreter and the lowering needed no change:

- **Prelude** ([[selfhost/checker.my]], `prelude_src`): `trait Iterator<T> { fun next(var self) -> Option<T> }`.
- **Bounds with arguments**: `TypeParam.bound_args` beside `bounds` ([[selfhost/ast.my]]); the parser reads `type_args` after each trait of a bound ([[selfhost/parser.my]], `generics`); the loader renames them as types ([[selfhost/loader.my]], `bounds`); `Bound.args` holds them resolved (`bounds_of`, under the function's or the impl's and method's type parameters). `validate_bounds` holds a bound to its trait's arity (`trait 'Iterator' expects 1 type argument(s) in the bound 'I: Iterator', got 0 (write 'I: Iterator<T>')`). An impl of a generic trait records its target and arguments (`impl_args`, by `trait\tkey`); `trait_args_of` gives a type's (its impl's, solved by its type arguments, `impl_trait_args`) or a type parameter's (its bound's). `solve_bounds` fixes, after each argument of a generic call or method, what a bound fixes once its parameter is known (`I: Iterator<T>` gives `T`), so the next argument's lambda takes `T`; `check_call_bounds` compares the arguments (`type 'Words' does not satisfy the bound 'I: Iterator<int32>' required by 'total': it implements 'Iterator<str>'`); `bound_method_call` takes a generic trait's methods with the bound's arguments. Natively `solve_targs` ([[selfhost/codegen.my]]) solves an instance's bound-only parameters from the same `impl_args`.
- **`for` over an iterator** (`check_for` → `is_iterator`, `check_for_iterator`): the checker builds D171's loop with new node ids, `if true { var %iter<id> = e; while true { match %iter<id>.next() { Some(x) => { body }, None => { break } } } }`, and checks it in place of the `for` (the iterable once, the hidden variable mutable, the body in the arm's scope with the loop depth raised). `fill_defaults` became `fill_in`: after the check it also puts that loop where the `for` was (`Fills { defaults, fors }`), so the interpreter's sync and async evaluators, the lowering and every target run an ordinary `while`/`match`, with the ownership, `break`/`continue`/`return`/`defer` and async (anf) handling those have. A choice made here, against the task's "in the interpreter and the lowering": one implementation of D171's meaning, not three. Lists, maps, strings and ranges keep `for_list`, `for_str` and the range loop.
- **Grammar**: `generic = IDENT ( ":" trait_bound ( "+" trait_bound )* )? ; trait_bound = IDENT type_args? ;` in `grammar/myla.ebnf` and [[Language/Grammar]]; tree-sitter regenerated (`grammar.js`, `src/`, the highlight query's `(trait_bound (identifier) @type)`).
- **Language server**: the bound's arguments resolve (`resolve.my`, definition of `P` in `I: Iterator<P>`), show in signatures (`symbols.my`, hover `fun first<I: Iterator<P>>(it: I) -> int`), and a loop variable over an iterator takes the type its `next` gives (completion after `p.`).
- **Messages**: `` `for ... in` requires a list, a map, a string, a range or an Iterator, found 'Countdown' (it needs 'impl Iterator<T> for Countdown') ``, and for a type parameter `(it needs the bound 'I: Iterator<T>')`.

Tests:

- `test_compiler_parity`: 188 tests pass (x86-64), new `iterators` (a user iterator, `Map`, `Filter`, `ListIter<T>`, `Words` yielding new strings, `for` with `break`, `continue` and `return`, a copy keeping its position, `total<I: Iterator<int>>`, `count<I: Iterator<T>, T>` and `to_list` whose `T` only the bound fixes, a method's bound, nested loops, a lambda), `iterators_async` (an `await` in the loop's body, `break`, `continue`), `iterator_adapters` (`Chain` over two iterators, a lambda typed by the bound, `for _`, `T: Add` beside `I: Iterator<T>`, a field looped over twice, `defer` in the body), all `PINNED`, and `test_iterators_release_what_they_yield` (a million pipelines of new strings: 11.3 MB peak). `MYLA_TEST_TARGET=aarch64-linux` and `wasm32-wasi` `-k iterator`: 4/4 each.
- The error corpus: [[examples/errors/type_bound_generic_trait_unsatisfied.my]], [[examples/errors/type_bound_generic_trait_arity.my]], [[examples/errors/type_for_over_non_iterator.my]], [[examples/errors/type_for_over_unbounded_type_parameter.my]], each with its `.stderr`; [[examples/errors/type_for_in_non_list.my]] reworded (its message changed), pinned now. A new example, [[examples/iterators.my]], registered in both example suites.
- The checker's cases: 649/649 (`bounds_of`, `trait_args_of`, `solve_bounds`, `is_iterator`, `check_for_iterator`, `fresh_id`, `impl_trait_args`, `bound_arity_msg`, `iterator_hint`); the parser 168/168, the AST 56/56, the loader 121/121, the code generator 342/342.
- `scripts/test.sh fast`: 665 tests, OK (1 skipped). `test_grammar` (with the tree-sitter CLI), `test_lsp`, `test_selfhost_cases`, `test_error_corpus`, `test_selfhost_checker`: pass. `test_lsp`'s corpus check that a local's use follows its declaration lets a bound name a type parameter declared after it in the same list (`<I: Iterator<T>, T>`).
- The other gates: `test_selfhost_parser`, `_interp`, `_lexer`, `_cli`, `_coverage`, `_floatlit`, `_codegen`, `test_declaration_recovery`, `test_native_runtime`, `test_aarch64`, `test_wasm`: pass. `test_selfhost_codegen`'s `error_at_module_member` (`for x in lib.N`) had the retired toolchain's "requires a list or map": its new message is pinned in `SUPERSEDED`.
- The bootstrap reaches its byte-identical fixed point (15,391,296 bytes). The compiler's own sources use none of the new syntax, so the current seed builds it; `selfhost/embedded_std.my` is unchanged (`lib/` is).

Measured (best of five, a machine shared with other agents): the sum of `3x` over the even `3x` for `x` in `0..n`, `int64`, MYLA-353's pipeline, consumed by `for` over the iterator and by `while let` and `next` written out:

| | Plain `while` loop | Lazy, `for` | Lazy, `while let` | Eager `xs.map(…).filter(…)` |
| --- | --- | --- | --- | --- |
| Native, n = 10 M | 35 ms, 11.5 MB | 77 ms, 11.5 MB | 85 ms, 11.5 MB | 330 ms, 233 MB |
| Interpreted, n = 300 k | 0.98 s | 18.8 s | 18.7 s | 4.6 s |

Natively the lazy pipeline is 2.2 times the hand-written loop and 4.3 times faster than the eager methods, in constant memory; the `for` costs nothing over `while let`. Interpreted it is 19 times the loop and 4 times the eager methods (MYLA-353 measured 12.8 s, best of three, under another load): each `next` is a method call with its `var self` copied back, once per adapter.

