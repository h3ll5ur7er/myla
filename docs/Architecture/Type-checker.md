# Type checker

[[src/myla/types.py]] holds the type representation, the `Checker`, the desugaring pass and the float-formatting algorithm shared by both back ends.

[TOC]

## Types

Frozen dataclasses, so they compare and hash structurally: `IntType(width, signed)`, `FloatType(width)`, `CharType`, `BoolType`, `StrType`, `StringBuilderType`, `StructType(name, args)`, `EnumType(name, args)`, `TupleType(elems)`, `ListType(elem)`, `MapType(key, value)`, `FuncType(params, ret)`, `TypeParam(name)` and `SelfType`. Aliases never survive resolution. `type_name` renders a type for messages.

## Passes

`check(program)` prepends the prelude (`Option`, `Result`, `get`) and runs `Checker.check()`:

```mermaid
flowchart TD
    a["_collect_globals<br/>name tables, duplicate and builtin-name checks"] --> b["_resolve_signatures<br/>aliases, struct fields, enum payloads,<br/>recursion classification, function signatures"]
    b --> c["_resolve_traits<br/>built-in operator traits, user traits"]
    c --> d["_synthesize_derives<br/>#derive(Eq) → impl Eq"]
    d --> e["_resolve_impls<br/>methods → functions Type.method,<br/>trait conformance, coherence"]
    e --> f["_validate_bounds"]
    f --> g["_fold_consts"]
    g --> h["_check_attributes_and_entry<br/>#main, #test"]
    h --> i["_check_function for every function and method"]
    i --> j["_desugar: splice in recorded replacements"]
```

Declaration order never matters, because every table is built before any body is checked.

The passes up to `_fold_consts` record each declaration part's error and go on, the part taking the error type or being left out (D84, [[MYLA-110]]; see "Going on after a declaration's error" below). After that each declaration's attributes, the entry point, each function body and then each method body is checked on its own (`_on_its_own`, from a clean state: loop depth, lambda stack, return type), and its first error is recorded; checking goes on with the next one, up to 20 errors (D80, [[MYLA-65]]). A function's errors cannot affect another's, since signatures come from the tables. `check` raises the first error found, with the others in its `more`, in that order: the declarations' errors in the order the passes find them, then attribute and entry-point errors, then free functions, then methods, each in declaration order (the entry file's declarations before the modules it imports). The self-hosted checker collects them the same way (`run_all`, `record`, `check_body`, `note`).

## Going on after a declaration's error

D84, [[MYLA-110]]. A part of a declaration that fails to check takes the **error type** (`ErrorType`, `ERROR`; self-hosted `Type.TError`) or is **left out**, and the passes go on (`_part`, `_record`, `_fail_part`; self-hosted `record`, `resolve_part`, `param_part`, `record_result`):

| Part | Failure | What remains |
| --- | --- | --- |
| a declaration | an import checked alone, a redefined builtin, a duplicate name or trait | the first one; the duplicate is left out, its body not checked (`_skipped`, by position) |
| a type in a signature, field, payload, trait method, impl target, const | unknown, wrong arguments, `Self` outside a trait, … | the error type for that part |
| an alias | a bad target, a cycle | the error type for the alias and every alias that names it, one error (`_resolve` caches it) |
| a field, variant or method | a duplicate, a method colliding with a field | the first one |
| type parameters, a recursive struct | shadowing, duplicates, infinite size | the declaration, as written |
| a `#derive` | not derivable, generic, a bad attribute, an explicit impl too | no derived impl; Eq is broken for the type (`_broken_impls`) unless an explicit impl stands |
| an impl | its target type failed or can't have methods; a duplicate impl | left out; its methods' and trait's names are lost (`_lost_methods`, `_lost_traits`) |
| an impl | an unknown trait; the trait's arity; conformance | its methods stay; the (trait, type) pair is broken |
| a bound | an unknown trait or type parameter | the bound is left out, and the function's body isn't checked |
| a const | any error in its type or value | its declared type (or the error type), no value; consts folded from it fail silently |

Bodies are checked as before. Where one depends on what failed, its check ends without an error (`_Poisoned`; self-hosted `poisoned()`, which `?` carries and `note` drops), since any error there would follow from the first:

- an expression whose type contains the error type (`_infer` wraps `_infer_node`), an assigned place (`_check_lvalue`) or a pattern (`_check_pattern`) of such a type;
- a call of a generic function or method, or a partial application, whose signature contains it; a generic struct or enum literal with such a field or payload;
- `?` in a function whose return type failed; a call or method value through a field whose type failed;
- a broken (trait, type) pair, or a lost trait, asked for by an operator or a bound (`_type_implements`); a method that isn't there but whose name a lost impl had;
- a call of a redefined builtin; a const folded from a failed one; a `#test` of a function whose signature failed.

Some parts are skipped rather than ending the check, since nothing else depends on them: the argument for a parameter of the error type (non-generic calls and methods), a field or payload of the error type in a literal, the value returned from a function whose return type failed, the initialiser of a `let` annotated with a failed alias (the binding has the error type), and a call statement whose result has the error type.

So no reported error follows from another, at the price of not checking the rest of a body after its first use of a failed part. The first error of a run is the one a single-error run reported, except where that one followed from a declaration error found later (an `impl Eq` for a misspelled type makes a `#derive(Eq)` that relies on it fail first; the derive is now left broken silently). `tests/burn/test_declaration_recovery.py` checks this on 674 mutants of the examples, each with one declaration broken: exactly the injected error is reported; the checker gate compares the self-hosted checker on the same mutants.

## Notes

An error can carry notes (D83, [[MYLA-65]]): `MylaError.notes` (`errors.Note`; the self-hosted `CheckErr.notes` and `Report.notes`, `tokens.Note`), each a `note` about another place in the same file or a `help` line without one. The CLI prints them after the error's line, a note with its own `-->` and carets; the canonical line a gate compares is followed by one `<label> <line> <col> <span>: <message>` line per note (`canon.canonical_note`, `diag.canonical_note`); the language server publishes a note as related information and appends a help line to the message; the REPL shows a note in the input against the input's lines.

| Error | Note |
| --- | --- |
| assigning to an immutable place, or calling a `var self` method on one | `'x' is declared here`, at the variable the place starts from (a `let`, a parameter, a lambda parameter, a destructured or match binding; none for a `for` variable or a method's receiver, which have no place of their own) |
| a variable declared twice in a scope, a top-level name declared twice | `'x' is first declared here` (not when the first is the prelude's) |
| a returned value of the wrong type | `the return type is declared here`, at the function's return type (not in a lambda) |
| an unknown name, function, type, field or method | `help: did you mean 'count'?` |

A suggestion is the candidate closest to the name in edits (inserting, deleting, replacing or swapping neighbouring bytes: `_edit_distance`, `edit_distance`), within a third of the name's length, so names under three bytes get none; of equally close candidates the alphabetically first. The candidates are what the name could have been: for a name, the variables in scope, constants, functions and the prelude's variants; for a call, functions, the built-in functions and variables; for a type, the primitive types, `int`, `float`, structs, enums, aliases and the type parameters in scope; for a field, the struct's fields; for a method, the type's methods. Methods' internal `Key.name` and the `__` primitives are never suggested.

## Inference

Inference is local and bidirectional: `_infer(expr, scope, expected)` returns the expression's type and records it as `expr.resolved_type`. The `expected` type is a hint, not a constraint; the caller compares the result.

- **Flexible literals.** An unsuffixed integer literal takes the expected integer type; `_unify` lets a literal operand adopt the other operand's type ([[src/myla/types.py#L3036-L3065]]). ASCII char literals may become integers the same way.
- **Generic calls** solve type parameters left to right with `_unify_param`, using each solved parameter type as the hint for the next argument, then verify every argument against the substituted parameter types (`_infer_generic_call`). Struct literals and enum constructors do the same with `_infer_type_args`, seeded by the expected type.
- **Lambdas** take parameter types from annotations or from an expected `FuncType`. Without an expected type, a block body's result type is collected from its `return`s (`_lambda_infer`).
- **Captures**: while a lambda body is checked, `_record_capture` adds every name that resolves to a scope outside the lambda's parameter scope to each enclosing lambda's capture list. Each lambda also gets a unique `lifted_name` for the native backend.
- **match** checks each arm in its own scope, then exhaustiveness and redundancy, then unifies the non-diverging arm values. Exhaustiveness and redundancy use Maranget's usefulness over pattern matrices: patterns are normalized to constructors (enum variants, `true`/`false`, the single constructor of a tuple or struct, literals) and wildcards, a match is exhaustive when a wildcard row isn't useful against the unguarded arms, and an arm is redundant when it isn't useful against the unguarded arms before it (`_useful`, [[MYLA-14]]; the same algorithm in [[selfhost/checker.my]]).

## Desugaring in the checker

| Source | Becomes | Where |
| --- | --- | --- |
| `e?` | `match e { Ok(v) => v, Err(x) => { return Result.Err(x) } }` (or the `Option` form) | `_infer_try`, `_build_try_match` |
| `f >> g` (functions) | `(__x: A) => g(f(__x))` | `_infer_compose` |
| `f(a, _)` | `(__hole0: B) => f(a, __hole0)` | `_infer_partial` |
| `a + b` on a struct/enum | `a.add(b)`; `==` → `a.eq(b)`, `!=` → `!a.eq(b)`, `<` → `a.cmp(b) < 0` | `_infer_operator_overload` |
| `#derive(Eq)` | a synthesised `impl Eq` (field-wise `&&`, or a `match` on `(self, other)`) | `_make_eq_impl` |
| `recv.m(x)` | stays a call, annotated with `method_func = "Type.m"` | `_infer_method_call` |

Synthesised lambdas get explicit parameter annotations (`_type_to_typeexpr`), so that the monomorphizer's second check doesn't depend on context. Operators on a bounded type parameter (`T: Add`) are not desugared; the interpreter dispatches at run time and the monomorphizer lowers them once `T` is concrete.

## Methods and traits

Every method becomes a function named `Type.method` (the dot can't occur in a user identifier) with a synthesised `self` parameter, registered in `functions` and in `methods[type_key]`. The key is the type's name, or the canonical name for built-in receivers (`int32`). Trait conformance substitutes `Self` (and a generic trait's parameters) and compares parameter and result types exactly. `trait_impls` records which user types implement which traits; primitives get built-in operator traits from `_primitive_default_trait`.

## Recursion classification

`_resolve_recursion` finds by-value cycles between aggregates. Every enum on a cycle is marked recursive (`recursive_enums`), which the native backend boxes; a cycle that remains once boxed enums are cut (only structs and tuples) is an "infinite size" error.

## Return analysis

`_block_returns` / `_stmt_returns` ([[src/myla/types.py#L3997-L4027]]) accept `return`, diverging calls (`panic`, `unreachable`, `__exit`) and `if`/`else` chains whose every branch returns. Loops and `match` statements don't count.

## Known gaps

None recorded; see [[Project/Known-issues]].
