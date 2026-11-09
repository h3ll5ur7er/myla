---
id: MYLA-406
title: "A struct field and a method of the same name: the field wins silently"
type: bug
status: review
priority: low
labels: [language, checker, diagnostics]
---
Found by the round 3 modules lane ([[MYLA-404]]): while `Lru` had a field `keys`, `c.keys()` didn't call the method `keys` but failed on the field, with a message that didn't say why. The lane renamed the fields (`slot_keys`, `slot_vals`).

- [x] Decide: a field and a method may not share a name (an error at the declaration, as Swift does), or a call `x.name()` resolves to the method (as Rust does)
- [x] The checker, an error-corpus file, and [[Language/Methods-and-traits]]

## What it was

D45 already said "method names unique per type and distinct from fields", and the checker held to it: `method 'keys' collides with a field of 'Lru'` at the method, the method left out. But every use of the left-out method was then reported too, `type 'Lru<str, int32>' has no method 'keys'`, an error that only followed from the first (against D84); a user of a module sees those at their own calls.

## Proposal (D178, for the owner)

**A method may share its name with a field, unless the field holds a function** (refines D45). `c.keys` is the field and `c.keys()` the method, as in Rust; there are no method values (D46), so `c.keys` without `()` is always the field. A field of function type keeps D45's rule: `h.on(x)` calls such a field (documented in [[Language/Functions-and-closures]]), so a method `on` beside it is the error `method 'on' has the name of a field of 'Handler' that holds a function: a call '.on(…)' would mean either`, with the help `rename the method or the field; a field that holds no function may share a method's name`. Calling a field that holds no function, where no method has its name, says why: `type 'Lru' has no method 'keys'` with `help: 'keys' is a field of type '[int32]', not a function: read it without '()'`.

Why: the getter named like what it reads is the common case: `Lru.keys`, an actor's state, which only its methods reach (`await counter.count()`), a trait method implemented from a field (`impl Named for Pet { fun name(self) -> str }` on a `name` field). It breaks no program, since none could have both.

Alternatives:
- **Rust's whole rule**: a method also beside a field of function type, `h.on(x)` the method and `(h.on)(x)` the field. Myla's parser drops parentheses (there is no `Paren` node), so `(h.on)(x)` and `h.on(x)` are the same tree, and the call would silently take the method; making the parentheses count needs a new node kind through every pass, or a side table, and changes what `h.on(x)` means once a method is added. Not worth it for a field of function type, which is rare.
- **Swift's rule** (D45 as it was): keep the error at the declaration and only drop the follow-on errors. Simplest, but it forbids the getter, the case the lane met.

A field of a type parameter (`struct Cell<T> { get: T }` with `fun get(self)`) is no function where the struct is declared, so the method is allowed; `c.get(…)` takes the method even where `T` is a function type.

## Evidence

- **Before** (the seed's checker): the parity program below failed with `method 'keys' collides with a field of 'Lru'`, `method 'len' …`, `… 'count' … of 'Counter'`, `… 'name' … of 'Pet'`, and the follow-on `type 'Lru<int32>' has no method 'keys'`: 6 errors. The language server's definition of `c.keys()` jumped to the field (`tests.burn.test_lsp …test_a_field_and_a_method_of_one_name` failed with the old [[tools/lsp/resolve.my]]: `{line 0, char 11}` for `{line 2, char 8}`).
- **After:** the parity program `a_field_and_a_method_of_one_name` (pinned; interpreter = x86-64 = aarch64 under qemu = wasm32 under node): `c.keys.len()` 3 and `c.keys()[0]` 3 (reversed), `c.len` 10 and `c.len()` 3, `cell.get` `q` and `cell.get().len()` 2, `await k.count()` 5 on an actor, `p.name` `rex` and `p.name()` / a bound's `x.name()` `pet rex`, and `h.on(2)`, `(h.on)(3)` through a field of function type, 3 and 4.
- **Checker** ([[selfhost/checker.my]], `resolve_impls`, `infer_method_call`): the collision check only for fields of function type (`is_tfunc_type`), with the help line; the call of a data field's help. **Language server**: a call `x.f(…)` resolves to the method and `x.f` to the field (`field(…, called)`, `member_type`), so definition, hover and references follow the checker.
- **Error corpus**: `examples/errors/type_method_field_collision.my` (now the function field's case, `//~ help:`) and `examples/errors/type_call_of_a_data_field.my`, both pinned (`.stderr`). The checker gate's recorded snippets `unit_test_13` and `unit_test_113` expected the old collision error: `SUPERSEDED` in `tests/burn/test_selfhost_checker.py`, with their new verdicts (the other errors of `unit_test_13`; `ok`).
- **Docs:** [[Language/Methods-and-traits#methods]] (the rule and a tested example), [[Language/Functions-and-closures]], the `myla` skill (both copies). D178's row is for the owner to add if they take the proposal.
- **Suites:** `tests.burn.test_error_corpus`, `test_selfhost_checker`, `test_compiler_parity`, `test_doc_blocks`, `test_lsp`; the bootstrap's byte-identical fixed point.
