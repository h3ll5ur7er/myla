---
id: MYLA-417
title: "P3b The checker: generic operators, literals, D178's call error, diagnostics"
type: bug
status: todo
priority: high
labels: [checker, diagnostics, round-5]
---
Work package P3 of [[Project/Review-2026-11-09]], the checker half that [[Project/Review-2026-11-10]] §5 splits off (wave A1). Files: `selfhost/checker.my`, the prelude's derives, the language server where a diagnostic changes. Reopens [[MYLA-367]]'s checker half and [[MYLA-394]].

- [x] M2, the checker's half: `infer_overload_known` substitutes, so `Box<int> + Box<int>` is `Box<int>`, not `Box<T>`
- [x] [[MYLA-394]]: D95 counts a mutator in the head of `if`, `while` and `match`
- [x] M24: `()` as a type argument ("expected '() -> ()', found '() -> ()'"); unblocks `std.bench` on closures that return nothing ([[MYLA-426]])
- [x] D178 (L1): where `x.f(…)` finds a method and the receiver's field `f` holds a function at that instantiation, the error `bind the field first: let g = x.f`
- [x] L2: an integer literal before the element that fixes a literal's type is re-checked against it (`[1, 300, 3u8]`, map keys too)
- [x] L5: `let w: uint8 = -1` is an error
- [x] L6: [[MYLA-401]]'s unfilled hole reported at the hole; [[MYLA-398]]'s `'shapes.Area' is a trait of module 'shapes', not a trait` and the bare name of an unsatisfied `T: b.Show`
- [x] [[MYLA-401]]'s quadratic join (64,000 `None`s then a `Some`: 40 s)
- [x] D182: `Option` and `Result` derive `Hash`
- [x] [[MYLA-379]]'s follow-up: `Tree.Leaf == t` types as `t == Tree.Leaf` does
- [x] [[MYLA-356]]'s follow-up: `r.and_then((x) => Ok(x + 1))` infers `E` from the receiver
- [x] [[MYLA-315]]'s follow-up: the expected type passes through `?`; no "add a type annotation" where the annotation is the problem
- [x] [[MYLA-380]]'s follow-up: an enum can be a stateful iterator
- [x] Diagnostics of §3.3: `'__list'`/`'__map'` and `__list.sorted` in messages ([[MYLA-320]], [[MYLA-383]]), `unmangled` on finished message text, "a enum … not a type", a hint towards `m.items()` for `for (k, v) in m` ([[MYLA-390]]), [[MYLA-371]]'s three misleading diagnostics, [[MYLA-384]]'s impossible hint for `Box.tag()`
- [x] [[MYLA-398]]'s language-server gaps

## What changed

- **M2** (`infer_overload_known`): an arithmetic operator's result is the impl method's under the receiver's arguments, `subst_type(ret, unify_param(params[0], lt))`. The native link error is [[MYLA-415]]'s half.
- **MYLA-394** (`Reentrancy.head`, `value_changes`): the head of an `if` or a `while`, a match's scrutinee and its guards make their mutators' changes before the head is examined; the statement's later `call_changes` skips what the match made. A mutator after an `await` inside one head counts as before it (the head has one epoch).
- **M24** (`subst_type`, `unify_param`): a function type whose result substitutes to `()` has none (D140), and a function without a result solves `T` of `() -> T` as `()`: `bench.run_n<()>("u", 3, () => work())` and `bench.run_n("v", 2, () => work())` run on all runners.
- **D178** (`field_shadowed`): the call error, at the call, for a field whose declared type names a type parameter and is a function at the receiver's instantiation (the field names are collected once, `tp_fields`).
- **L2 and the quadratic join** (`column_step`, `open_column`, `drop_columns`): a column's open elements and its literals live in the checker (`col_open`, `col_lits`), added to in place; they were fields of the column, a value copied at every element. While only literals (`adapts`: an unsuffixed integer, float or char literal, or a negated one) are in a column, an element of another type gives its type to them, each checked again; a column that a non-literal fixed no longer adopts a later element's type (`[1, x, 3u8]` with `x: int32` was accepted). `[-1, 3i8]` is an `[int8]` now.
- **L5** (`infer_unary`): `-n` of a literal `n > 0` of an unsigned type is `integer literal -1 does not fit in 'uint8'`.
- **L6**: `hole_at` reports the innermost element where the joined type keeps a hole; `trait_text` names a bound's trait with its module when another trait has the name (`T: b.Show`); in [[selfhost/loader.my]] (P4's file, one message each) `'m.T.U'` says `only a module has members`.
- **D182** (prelude, `prelude_need`): `Option` and `Result` are `#derive(Eq, Hash)`. The bodies of the four derived impls wait, as an implicit module's do, until checked code compares or hashes a type that holds an `Option` or a `Result`: `==` (`infer_overload_known`, the tuple and list `==`), a map's key (`check_key`, an index), a generic call's or method's type arguments, a derived non-generic `Eq`'s members (`members_need`), a tuple's `hash`; a direct `o.eq(x)` or `o.hash(h)` calls them by name. Checked eagerly they cost a hello world 1.4 % (std.hash's `add` and `add_u64` with them). The explicit `Eq` and `Hash` impls' targets are found once in `synthesize_derives`, not once per derived type.
- **MYLA-379's follow-up** (`other_side_first`): a variant of a program's enum on the left of `==` is typed by the right side.
- **MYLA-356's follow-up** (`arg_hint`, `partial_result`, `infer_lambda`): a lambda argument whose parameters are known gets its result's known part as a hint, the open type parameters as holes, for an expression body only; a result that keeps a hole is an error at the body. Block bodies are unchanged.
- **MYLA-315's follow-up** (`try_hint`, `result_clash`): `e?` expects `Result<X, E>` of `e` (the function's `E`) or `Option<X>` when `X` is expected of it; a generic call whose declared result can't be the expected type says so (`its result 'B<T>' can't be the 'int32' expected here`) instead of asking for an annotation.
- **MYLA-380's follow-up**: an enum's (non-async) `var self` method may assign `self`, which writes the caller's place as a built-in value's does (D144): interpreted, natively, on aarch64 and wasm32 alike.
- **Diagnostics**: `unmangled_in` rewrites only the qualified names the checker knows (`known_names`) and writes `__list`/`__map` as `[T]`/`[K: V]`; `for (k, v) in m` on a map with non-tuple keys says the loop visits its keys, with `help: write 'for (k, v) in m.items()'`; the static-call hint for a generic type is `impl<T> Tag for Box<T>`; "a enum … not a type" was already "an enum" since [[MYLA-398]].
- **Language server** ([[tools/lsp/resolve.my]]): `T.` with `T: g.Zero` lists the module trait's functions (`module_trait_members`).

## Proposal (an open decision)

[[MYLA-371]]'s "three misleading diagnostics" aren't spelled out in the review. I took the dotted-type messages I found misleading: a variant as a type (`'Shape.Dot' is not a type: 'Shape' is an enum, and only a module has members`, it said `unknown module 'Shape'`), a module as a type (`'deque' is a module, not a type`, it said `unknown type 'deque'`), both fixed in the loader, and `deque.Deque.Item` (`only a module has members`, L6's). Two stay: a call of what a module doesn't export, `module does not export 'Nope'`, doesn't name the module, but `test_selfhost_codegen`'s gate holds that message to the retired Python loader's recording (`member_not_exported`), so naming the module needs the recording re-pinned, the owner's call; and `deque.Deque { … }` is a parse error (`expected newline, ';' or '}'`), the parser's (P3a). Alternatives: leave the loader alone and only file them; or make `m.T { … }` literals work (a language change, D170 says they need `from … import`).

## Evidence

- **Tests first**, each failing before (the base compiler `57fa3ef`, or the `#test` case against the base code) and passing after:
  - `selfhost/checker.my` cases (866 → 919, all pass): `errors_of` M2 ×2, L2 ×8, L5 ×4, D178 ×4, `Tree.Leaf` ×2, L6 hole, enum `self` ×3; `warnings_of` MYLA-394 ×6; `subst_type` ×2, `unify_param` ×2 (M24); `adapts` ×6, `holds_prelude_enum` ×3, `try_hint` ×4, `result_clash` ×4, `partial_result` ×3, `type_params_named`, `place_text` ×3, `unmangled_in` ×4, `static_hint` +1, `impl_head` ×2. Before: `errors_of #43: expected [], got ["cannot assign value of type 'Box<T>' to binding of type 'Box<int32>'"]` and the like.
  - Parity programs (`tests/burn/test_compiler_parity.py`, pinned, interpreted = native): `unit_as_a_type_argument`, `literals_take_the_type_a_later_element_fixes`, `option_and_result_as_map_keys`, `inference_through_lambdas_try_and_variants`, `enum_var_self_assigns_self` (also run on aarch64 under qemu and on wasm32 under node: the same output, as `option_and_result_as_map_keys`).
  - `tests/burn/test_prelude_impls.py` (new): eleven programs, each comparing or hashing an `Option` or a `Result` one way only, interpreted and native. With `members_need` disabled, `a derived Eq's member` fails natively: `internal error: Option.eq__4.str can't be lowered to the IR`.
  - `tests/burn/test_literal_columns.py` (new): 4,000 and 16,000 elements of `None`s then a `Some`, of literals then `3u8`, of map keys, within eight times the time. Base: 4,000 `None`s 0.073 s, 16,000 1.70 s (23×), 64,000 37.6 s; after: 64,000 0.15 s, 64,000 literals 0.14 s, 64,000 map keys 0.32 s.
  - Error corpus (pinned `.stderr`): `type_literal_before_the_element_that_fixes_the_type`, `type_map_key_before_the_key_that_fixes_the_type`, `type_negative_literal_unsigned`, `type_method_beside_a_function_field`, `type_literal_hole_reported_where_it_is` (col 21, the unfilled `None`; it was col 15), `type_generic_result_against_the_annotation`, `module_type_member_of_a_type`, `type_for_tuple_over_a_map`, `type_duplicate_list_method_names_the_list`, `type_format_spec_keeps_its_text`, `module_variant_as_a_type`, `module_module_as_a_type`, `type_generic_static_call_hint`.
  - `tests/burn/test_lsp.py`'s new `test_a_module_trait_s_functions_on_a_type_parameter`: before `[] != ['one', 'zero']`.
- **Reproducers**: `bug_generic_add_type` 3, `chain_add` 1, `bug_unit_closure` 3 (also natively), `m394_missed_heads` warns at the three heads, `lit_adopt_min` and `neg_u8` are errors at the literal, `gap_and_then` true, `gap_expected_through_try` checks past its `?` lines (its `acc.items += lst()` is no Myla: lists have no `+`), `e_enum_iter` 2 1 0, `g1/after` the D178 error, `err24` at 11:21, `e7` and the `b.Show` program as above, `e_u1` keeps `std$iter$sum`, `bug_diag_list_name` names `[T]`.
- **Check time** (callgrind, `build/myla check`, instructions): hello world 39,366,219 at the base → 39,260,079; with `std.io` 101,174,506 → 101,011,136. (D182 with its bodies checked eagerly was 39,924,165; lazily, before the derive loops and the D178 check were made cheaper, 39,705,725.)
- **Bootstrap**: `scripts/bootstrap.sh` reaches its fixed point after every commit.
- **Suites**: `scripts/test.sh fast` 784 tests OK (3 skipped) after the D182 commit; `tests.burn.test_error_corpus` 336 OK, `tests.burn.test_lsp` 166 OK, `tests.burn.test_builtin_impls` OK, the new parity programs OK; the full `scripts/test.sh`: 1,424 tests, 336 skipped, two failures, both fixed or explained: `test_selfhost_codegen`'s `member_not_exported` (my message naming the module, reverted, see the proposal; the test then passes) and `test_aarch64`'s `t27_children_read_as_they_write`, a 120 s qemu timeout under the five lanes' load that passes run alone.

## Found on the way

- [[MYLA-448]]: `m[Ok("a")] += 1` can't infer the key's type (the parser's hoisted `let %index`).
- [[MYLA-449]]: a literal before the element that fixes a wider type must still fit `int32` (`[4000000000, big]`).

## The owner's decision (2026-11-11)

The proposals stand as built (D189). The message of a module's member it doesn't export now names the module, as the owner asked: `module 'std.deque' does not export 'Nope' (declarations are private unless marked 'pub')`, with `member_not_exported` re-pinned in `test_selfhost_codegen`'s `SUPERSEDED` and a new error-corpus file, `examples/errors/module_member_not_exported.my`. `deque.Deque { … }` stays a parse error (D170).

## Review 2026-11-12

Reopened ([[Project/Review-2026-11-12]]): two regressions, both narrow. The rest holds: 4,708 generated literal programs with none wrong, 174 diagnostics without an internal name, and the package's tests catch mutations of its fixes.

- [ ] **D178's call error fires on a generic actor's getter called from outside** (new). The field can't be meant there, as an actor's state is private, and the fix the message gives (`let g = c.value`) is itself an error; the compiler before round 5 prints 6. `field_shadowed` should skip an actor receiver that isn't `self`. Reproducer `repro-r5/checker/bug1_d178_actor_getter.my`:

  ```myla
  actor Cell<T> { value: T }
  impl<T> Cell<T> {
      fun value(self) -> T { return self.value }
  }
  #main
  async fun main() {
      let c = Cell { value: (x: int) => x + 1 }
      let f = await c.value()
      print(f(5))
  }
  ```
- [ ] D95's head, which [[MYLA-394]] carries (the same function, `Reentrancy.head`)
