---
id: MYLA-401
title: "A list literal's element type isn't taken from its later elements"
type: improvement
status: review
priority: low
labels: [language, types, checker]
---
Found by the gaps lane ([[MYLA-379]]). A list literal types its elements by the first one, so a generic variant whose first element leaves a type parameter open fails, though a later element fixes it:

```myla
enum Either<L, R> {
    Left(L),
    Right(R),
}

fun main() {
    let es = [Either.Left(1), Either.Right("a")]
    print(es.len())
}
// output:
// 2
```

`type error: cannot infer type parameter(s) R; add a type annotation to guide inference` at `Either.Left(1)`. With the list's type written (`let es: [Either<int, str>] = …`) it checks. The same holds for a struct literal's field holding such a list, `Page { items: [Tagged.One(p)], next: None }` as a `Page<Tagged<Point, bool>>`.

- [x] A list (and map) literal's element type unifies its elements' types, a variant's open type parameters taken from a later element, as Rust does; or the message says that the list's type fixes it

## Evidence

- **What changed** ([[selfhost/checker.my]], `infer_list_lit`, `infer_map_lit`, `column_step`, `close_column`, `fill_open`; [[Language/Generics#type-arguments]] item 4, [[Architecture/Type-checker#inference]]): while a list's element (a map's key or value) is checked, `open_at` holds its node id, and a variant, a struct literal, an empty list or map, or a list, map or tuple literal that is itself such an element leaves the type parameters nothing fixes as holes (`TParam("?")`, a name no program writes) instead of failing. The column's type joins the elements' (`join_open`); what an earlier element fixed hints the later ones (a hint with a hole only to an element that can take it). At the end the elements that had holes get the joined type in `resolved`, nested ones too, and a map's key type a later key fixed is checked then; nothing is checked twice, no hole reaches a back end. A hole nothing filled is reported by checking the first open element again on its own, so the message is the one it always was.
- **Now accepted** (the parity program `literal_element_types_from_later_elements`, pinned, interpreter = x86-64 = aarch64 under qemu = wasm32 under node): `[Either.Left(1), Either.Right("a"), Either.Left(3)]`, `[None, Some(2u8), None]` (its `Some` a `uint8`: `v + 250` is 252), `[Ok(1), Err("bad"), Ok(2)]`, `[Tagged.Nothing, Tagged.One(1.5), Tagged.Two(2.5, 'x')]`, `[[], [Either.Left(4)], [Either.Right(true)]]`, `[[], [], [7i64]]`, `["a": None, "b": Some(2), "c": None]`, `[Key.Any: 1, Key.One('z'): 2]` (a `#derive(Eq, Hash)` generic key, checked once fixed), `[(None, 'a'), (Some("b"), 'c')]`, `Page { items: [Tagged.One(1), Tagged.Two(1, false)], next: None }`, and `[Either.Left(1u8), Either.Left(2), Either.Right("x")]` (the `2` a `uint8`).
- **Before:** the same program failed `build/myla check` with `type error: cannot infer type parameter(s) R; add a type annotation to guide inference` at line 33 (`Either.Left(1)`); `[None, Some(1)]` with `cannot infer type argument(s) for 'None'`.
- **Errors kept:** `[Either.Left(1), Either.Left(2)]` still says `cannot infer type parameter(s) R` at the first element (`examples/errors/type_list_elements_leave_param_open.my`, pinned); `[None: 1]`, `[[], []]`, `[Tagged.Nothing, Tagged.One(1)]` give their old messages; `[Key.Any: 1, Key.One(1.5): 2]` is `map key type must be Eq and Hash, found 'Key<float64>'`. An open element of another type is `type mismatch: 'Option<_>' vs 'int32'`, the open parameter as `_` (`examples/errors/type_list_open_element_mismatch.my`, pinned).
- **Not covered:** a hole inside a variant's payload (`[Some(None), Some(Some(1))]`) or a call's argument still needs the hint from where it stands, as before; `[Either.Left(1), Either.Left(2i64), Either.Right("a")]` is a mismatch (`int32` against `int64`), as `[Some(1), Some(2i64)]` was: only a literal standing alone as the first element adopts a later one's type.
- **Suites:** `tests.burn.test_error_corpus`, `test_selfhost_checker`, `test_compiler_parity`, `test_doc_blocks`: 557 tests OK; the bootstrap reaches its byte-identical fixed point.
