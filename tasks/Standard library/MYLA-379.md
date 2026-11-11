---
id: MYLA-379
title: "Small gaps wave 3 met: == on Option and Result, IoError's Format, #derive on generic types"
type: improvement
status: done
priority: low
labels: [language, stdlib]
---
Found by several wave 3 lanes ([[Project/Standard-library-roadmap]]). Each cost a private helper in more than one module.

- [x] `==` on `Option<T>` and `Result<T, E>` when their payloads are `Eq` (lanes MYLA-341, MYLA-345, MYLA-344, MYLA-343 compare through `match` helpers)
- [x] `IoError` has no `message()` or `Format` (D168): adding them changes how `f"{e}"` and the test reports show one, so a decision on the text first
- [x] `#derive(Eq, Hash)` on a generic type is "not supported yet" ([[MYLA-342]]: `Grid<T>` has no `==`)
- [x] `std.io.copy` reads 4 KiB at a time; a large copy wants a bigger buffer or a size parameter ([[MYLA-339]])

## Decided (D173, 2026-11-09)

`IoError`'s text: `message()` and `Format` give a lowercase description with the cause after it, `not found (NotFound)`, `error 5 (Other(5))`. Built in batch 5, after [[MYLA-385]].

## What was built

- **`#derive` on generic types.** `#derive(Eq)`, `#derive(Hash)` and `#derive(Json)` take a generic struct or enum. As MYLA-385's Json derive does, the impl is written as source (`derived_eq_src`, `derived_hash_src` with a head, `derived_json_struct_src`/`derived_json_enum_src` with the type parameters), against the linked program's names (`parse_qualified`), and resolved and checked with the other impls; every type parameter is bounded by the trait (`impl<A: Eq, B: Eq> Eq for Pair<A, B>`, `impl<T: Hash> Hash for …`, `impl<T: ToJson> ToJson for …` and `impl<T: FromJson> FromJson for …`). A concrete type's `Eq` stays the runners' structural comparison.
- **A generic impl's bounds hold at the use** (`impl_bounds`, `impl_bound_failing`, `failing_arg`): a type has a trait when its impl's bounds are met by its arguments, for a written impl too. Before, `impl<T: Eq> Eq for Box<T>` let `Box<NoEq> == …` through the checker. The operator's, the map key's and a call bound's messages name the argument that fails (`operator '==' is not defined for 'Pair<int32, Pos>': 'Pos' isn't Eq (…)`; `type 'Page<Pos>' does not satisfy the bound 'T: ToJson' required by 'encode': 'Pos' isn't ToJson` with the derive's help for `Pos`).
- **`==` on `Option` and `Result`**: the prelude's `Option` and `Result` are `#derive(Eq)`. `==` types its right side by its left one (`opt == None`), and a left side of `None`, `Some(…)`, `Ok(…)` or `Err(…)` by the right one (`None == opt`).
- **Natively**, a routine on a generic type's values (a member's `eq` or `hash` in a tuple's, a list's, a derived struct's or a key's routine) calls its impl's instance for the type's arguments (`CodeGen.type_method`); before, it called `Box.eq` and the program didn't link (`undefined reference to 'myla_Option.eq'`, for a written generic impl too). A derived `Hash`'s key walk substitutes the arguments into the members' types. The interpreter compares a derived generic type structurally.
- **The match helpers go**: std.grid's `is`, std.btree's `is_some_of`, `same_entry`, `same_value`, std.compress's `shown`, `shown_some`, `shown_bytes` (its `agree`, a `Result` against an `Option`, stays), std.bigint's `reads_back` is one `==`. std.text had none. std.map's `holds` and std.args's `is` stay until the seed knows `==` on `Option` ([[MYLA-400]]): the toolchain compiles those two modules with the seed, and the bootstrap's embed step failed with them gone.
- **`Grid<T>` derives `Eq` and `Hash`**, so grids compare and are map keys (MYLA-342's case).
- **D173**: `IoError.message()` and `impl Format for IoError`, on `io_error_name`: `not found (NotFound)`, `directory not empty (NotEmpty)`, `address in use (AddrInUse)`, `error 5 (Other(5))`. A test function's report shows it (`FAIL  fails_with_an_io_error: not found (NotFound)`, the two pinned reports updated).
- **`std.io.copy`** reads 64 KiB at a time (`COPY_CHUNK`).
- Json on generic types didn't need [[MYLA-398]]: the generated source names the traits by the loader's qualified names (`T: std$json$ToJson`), which `parse_qualified` takes.

## Proposals (not settled in Decisions)

1. **The derived bound is the trait on every type parameter** (Rust's rule), even one no field uses. The alternative, bounding only the parameters the fields name, admits more types but makes the impl's requirements depend on the fields' shapes; not worth it until someone meets a phantom parameter.
2. **`Option` and `Result` are `Eq` but not `Hash`**: the task asked for `==`; making them map keys too is a one-word change to the prelude (`#derive(Eq, Hash)`) whose cost is a derived `hash` in every program that hashes one. Recommend leaving it until a program wants an `Option` key.
3. **`None == opt` works**, by typing the left side from the right when the left is a bare `None`/`Some`/`Ok`/`Err`; the alternative is to require `opt == None` only. Recommend keeping it: it is what Rust accepts and costs one branch.
4. **D173's words for each cause**: the description per variant is mine (`directory not empty`, `address in use`, `address not available`, `unsupported`, `invalid data`, `error N` for `Other(N)`), after Rust's `io::ErrorKind` texts.
5. **`copy`: a bigger default, no size parameter.** 64 KiB, between Go's 32 KiB and coreutils' 128 KiB; 128 KiB measured 3 ms better on 256 MiB, not worth doubling each read's string. A `copy_with(r, w, size)` can come when a program needs another size.
6. **`IoError` isn't `Eq`** (std.io's and std.compress's tests compare it by code or by text). `#derive(Eq)` on it would let `r == Err(IoError.NotFound)` work; left for the platform lane's std.fs work or the owner.

## Evidence

Built on `eaa905d`; commits `d81384a`, `cdb47b1`, `491ed47`, `81fc9d0`, `d6ca91e`, none of them staging.

- **Tests first**, run with the tools of `eaa905d`: [[tests/burn/test_compiler_parity.py]]'s `option_result_equality` failed (`cannot derive Eq for struct 'Holder': field 'tag' has type 'Option<str>', which is not Eq`; on its own `a == Some(3)` was `operator '==' is not defined for 'Option<int32>'`), `derive_on_generic_types` and `json_derive_generic` failed (`deriving on generic types is not supported yet …`), `io_error_text` failed (`format() cannot render a value of type 'fs.IoError'`). After: all four pass, native output = the interpreter's = the pinned one on x86-64; the same programs built with `--target aarch64-linux` under qemu and `--target wasm32-wasi` under Node print the interpreter's output.
- **Error corpus**, pinned with `.stderr`: [[examples/errors/type_option_payload_not_eq.my]], [[examples/errors/type_derive_generic_argument_not_eq.my]], [[examples/errors/type_derive_generic_key_not_hash.my]], [[examples/errors/type_derive_generic_field_not_eq.my]], [[examples/errors/type_derive_json_generic_argument.my]] (with its help); `type_derive_json_generic.my`, which pinned the old refusal, went. `test_error_corpus` 309 OK.
- **The checker's cases**: `derived_eq_src` (4), `with_params` (2), `bounded_params` (2), `derived_hash_src` with a generic head, `derived_json_struct_src` of a generic type, `type_params_of` (2), `impl_bound_failing`, `failing_arg`, `needs_other_side` (3), `is_none_tt` (2), two `errors_of` programs; `selfhost/checker.my` 760/760, `selfhost/codegen.my` 350/350, `selfhost/lower.my` 115/115. `test_selfhost_checker`'s `derive_on_generic` is `ok` now; its `derive_and_impl` caught the prelude's derive hiding a program's first `#derive` in `check_program`, whose node ids start at 0 as the prelude's do (fixed in `d6ca91e`).
- **Modules**, interpreted, `--native`, `--target aarch64-linux` and wasm32: std.grid 13/13 (`==` and a `[Grid<int>: int]` map added to `cells`), std.btree 8/8, std.compress 136/136, std.io 24/24 (a copy of more than 64 KiB added), std.fs 71/71 (`message` 5 cases, `format` 1); std.bigint 140/140 interpreted and native (138 since [[MYLA-396]] took two of its bit-count helpers).
- **`copy`**, a 256 MiB file, best of seven, native x86-64: into a new file 162 ms before → 88 ms after, to `/dev/null` 56 → 40 ms; the copy is byte-identical. Chunk sizes measured with the same loop: 4 KiB 157/56, 16 KiB 104/42, 32 KiB 95/41, 64 KiB 91/40, 128 KiB 85/39, 256 KiB 84/43 ms (file/null). 50 MB from one memory stream to another: 235–290 ms before, 230–266 after (unchanged).
- **Check time** of a hello world (`myla check`, three interleaved rounds of 15, medians): before 68, 63, 56 ms; after 56, 60, 60 ms: the prelude's two derived impls are within the noise.
- `scripts/test.sh fast`: 732 tests OK (3 skipped). `python3 -m unittest tests.burn.test_compiler_parity tests.burn.test_selfhost_cases tests.burn.test_error_corpus tests.burn.test_selfhost_checker tests.burn.test_lsp tests.burn.test_std_modules tests.burn.test_fs`: 718 tests, one failure (`derive_and_impl`, fixed by `d6ca91e`; `test_selfhost_checker` 7/7, `test_error_corpus` and the changed parity programs re-run OK after it). `test_test_functions`, `test_test_native`, `test_doc_blocks`: 22 OK. All with the regenerated `selfhost/embedded_std.my`, restored to the seed's for the commits (D156).
- The bootstrap reaches its byte-identical fixed point (18,611,222 bytes).
- Docs: [[Language/Types]] (the equality table, `Option`/`Result`), [[Language/Expressions-and-operators]], [[Language/Generics]], [[Language/Methods-and-traits]] (a tested block of generic derives), [[Language/Attributes-and-testing]], [[Language/Standard-library/Json]], [[Language/Standard-library/Grid]], [[Language/Standard-library/Fs]] (a tested block printing an `IoError`), [[Language/Standard-library/Io]] (the measurement), [[Architecture/Type-checker]]; the `myla` skill, both copies.

## Found on the way

- [[MYLA-401]]: a list literal's element type isn't taken from its later elements (`[Either.Left(1), Either.Right("a")]`).
- [[MYLA-400]]: std.map's and std.args's Option helpers wait for the seed.
- Fixed here: a written generic impl's bounds weren't checked at an operator (`Box<NoEq> == …` compiled), and a written generic `eq` inside a tuple, a list or a derived struct didn't link natively.

## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]], with a follow-up in [[MYLA-417]]: `Option`/`Result` aren't `Hash` (D182); `Tree.Leaf == t` fails where `t == Tree.Leaf` works.
