---
id: MYLA-373
title: "Explicit type arguments on a call, parsed speculatively (D169)"
type: feature
status: review
priority: medium
labels: [language, parser, checker, generics]
---
The owner's choice for [[MYLA-315]]'s open box, recorded as D169: `mk<int>()`, `deque.new<str>()`, `xs.mapped<str>(f)`. After a name or a method's name in an expression, `<` is tried as a type-argument list and kept when it closes with `>` and the next token is `(`; otherwise the parser goes back and reads a comparison. The design notes are in MYLA-315's "Explicit type arguments" section.

- [x] The parser: the speculative type-argument list on a call and a method call (its errors during the attempt dropped), the AST's call node carrying the types
- [x] The grammar (`grammar/myla.ebnf`), [[Language/Grammar]], the tree-sitter grammar generated from it (`test_grammar`)
- [x] The checker: the explicit arguments seed `infer_generic_call`'s and `infer_generic_method`'s substitution; a count that doesn't match is an error; a method's arguments name its own type parameters
- [x] Every runner: the instance is the one the arguments name (the native backend's `solve_targs` reads the checked types)
- [x] Tests: parity programs (`let d = deque.new<int>()`, a call statement, `a < b` and `f(a < b, c > d)` still comparisons), error-corpus files for a count mismatch; [[Language/Generics]] and the skill

## Evidence

- **The rule as built** ([[selfhost/parser.my]], `postfix`, `explicit_type_args`, `type_args_ahead`): at a `<` whose previous token is an identifier and whose expression so far is a name or a member (`f`, `m.f`, `x.method`; not `(a)` nor `f(x)`), a scan of the tokens checks that only a type's tokens follow, the `<`/`>` balanced, up to a `>` right before `(`; then the type arguments are parsed with the position, node ids, nesting depth and pending error saved, and kept only when they parsed without an error and `(` follows. Otherwise everything is restored and the `<` is a comparison's. The call node is `ExprKind.Call(callee, args, targs)`; the canonical dump shows `targs` only when there are some, so the recorded dumps still hold.
- **Ambiguity.** `a < b > (c)` is now a call of `a`; as a comparison it parsed before but was never well typed (a comparison is a `bool`, and a `bool` isn't ordered, even with an `impl Ord for bool`: checked). The one reading a valid program loses is C#'s: `f(a < b, c > (d))` is one generic call `a<b, c>(d)`, not two comparisons; `f(a < b, c > d)` and `f((a < b), c > (d))` stay two. Pinned in `dump_expr`'s cases (`a < b > c`, `a < b >= (c)`, `(a) < b > (c)` compare) and written on [[Language/Grammar]] and [[Language/Generics]].
- **The checker** (`explicit_subst`): the explicit arguments are resolved and seed the substitution before the receiver, the arguments and the expected type; their count must be `own_type_params` (a new `FuncSig` field: a method's own, the last of its combined type parameters, not its impl's). A non-generic function or method, a method with only its impl's type parameters, a builtin, a variant or a function value given type arguments is an error. Each argument's resolved type is kept under its node, and `solve_targs` reads it, so a type parameter only the explicit arguments name gets its instance natively too.
- **Test first.** Before the change the parity program fails to parse: `parse error: expected an expression, found 'str'` at `mk<str>()` (`mk<int>()` parsed as `(mk < int) > ()`).
- Parity: `explicit_type_arguments` (pinned `0 1 0 5000000000 8 seven <3> 0 0 0 hi 200 true true true lt true true`: a call statement, `let` without annotation, an `int64` literal through `widen<int64>`, two type arguments, a method's own `mapped<str>` with a lambda, `emptied<char>()`, `mk<B<int>>()` closed by `>>`, `mk<T>()` in a generic function, an argument of a generic call, comparisons in arguments, `x << 3 > y`, an f-string hole) and `test_explicit_type_arguments_of_a_module` (`deque.new<int>()`, `set.new<str>()`, `d.emptied<str>()`, `deque.of<int64>([5000000000])`, a call statement `set.new<bool>()`): interpreter and native agree. `scripts/test-target.py aarch64-linux test_compiler_parity`: OK; `wasm32-wasi`: OK but for MYLA-371's new test, which ran against this commit's tree before MYLA-371 existed.
- Error corpus with pinned `.stderr`: `type_explicit_type_args_count` (`function 'mk' expects 1 type argument(s), got 2`, underlining `int, str`), `type_explicit_type_args_method_count`, `type_explicit_type_args_impl_params`, `type_explicit_type_args_not_generic`, `type_explicit_type_args_on_builtin`, `type_explicit_type_arg_against_argument` (`widen<str>(true)`). `test_error_corpus`: 270 tests, OK.
- Own cases: `build/myla test selfhost/parser.my` 165/165 (new: `explicit_type_args`, `type_args_ahead`, `names_a_callee`), `selfhost/checker.my` 633/633 (new: three `infer_call` cases, `callee_words`), `selfhost/ast.my` 56/56 (`call_targs`, seven `dump_expr` cases).
- `test_grammar` (with tree-sitter): 10 tests, OK; the grammar has `generic_call` in `primary` and in the new `member` rule, with two declared conflicts so tree-sitter keeps both readings. `test_selfhost_parser`, `test_selfhost_checker`, `test_std_modules`, `test_doc_blocks`, `test_lsp` (`test_explicit_type_arguments`: definition on `P` in `mk<P>()`): OK.
- `scripts/bootstrap.sh`: byte-identical fixed point (13,760,424 bytes). No seed: the integrator's last commit runs `scripts/update-seed.sh` (D156).

## Review 2026-11-09

Not ready ([[Project/Review-2026-11-09]]): `f"{a < b} {c > (a)}"`, `[a < b, c > (d)]` and tuples are parsed as one generic call, and the look-ahead is quadratic (M1; D186). The fix is in [[MYLA-416]].

- [x] The review's blocker, fixed with [[MYLA-416]]: a comma ends the type-argument scan in a list, map or tuple literal's element and before each f-string hole (whose brackets close in it), and the scan has a budget of 128 tokens; `f"{a < b} {c > (a)}"` prints `true true`, 32,000 comparisons in a list parse in 0.14 s (13 s before). Evidence in [[MYLA-416]].
