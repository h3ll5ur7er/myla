---
id: MYLA-507
title: "Checker: a derived `eq` that can't compare a field is reported in `std/hash.my`, with a fix that can't be written"
type: bug
status: done
priority: low
labels: [checker, derive, diagnostics]
---
Found by [[MYLA-436]]'s lane. `#derive(Eq)` on a generic struct gives `impl<T: Eq> Eq for P<T>`; when a field's type has `==` only under another bound (here `W<T>`'s written `eq` needs `T: Ord`), the derived `eq` doesn't check, and the error is reported at a position of the standard library, not at the `#derive` or the field:

```myla
struct W<T> {
    v: T,
}

impl<T: Ord> Eq for W<T> {
    fun eq(self, other: W<T>) -> bool {
        return !(self.v < other.v)
    }
}

#derive(Eq)
struct P<T> {
    w: W<T>,
}

fun main() {
    print(P { w: W { v: 1 } } == P { w: W { v: 2 } })
}
```

```
type error: operator '==' is not defined for 'W<T>': 'T' isn't Ord (it needs the bound 'T: Ord')
  --> <myla>/std/hash.my:3:23
```

The synthesized impl's positions are read in the wrong file (line 3, column 23 is no expression of the program either), and the help asks for a bound a struct can't carry (`type-parameter bounds are not supported on a struct`) and a derive can't add.

- [x] The error points at the `#derive(Eq)` (or the field `w`) of the user's file
- [x] The text says what to do instead: write `impl<T: Ord> Eq for P<T>` by hand (or, a decision: a derive takes the bounds its fields' impls need)
- [x] A case in `examples/errors/` with its pinned `.stderr`

## What changed

- The impls the derives write are now recorded with the derive that wrote them (`Checker.derived`, `DerivedImpl`). A new phase after `validate_bounds`, `check_derived_fields`, checks each derived impl's fields under the derive's own bounds once every impl's bounds are known (`derive_lacks`, `impl_lacks`). It looks only at types that hold a generic struct or enum (`has_generic_member`). A field that lacks a bound refuses the derive at its struct or enum, where the other derive errors are reported (`cannot derive Eq for struct 'P': field 'w' has type 'W<T>', which is Eq only where 'T: Ord'`). Its help gives the impl to write by hand (`write the impl instead: 'impl<T: Eq + Ord> Eq for P<T>'`; for `Json` and `Toml`, "write both impls instead"). The derived impl is then left out (`skip_derived`), so its body's error isn't reported at all.
- A concrete argument that misses its impl's bound is refused in the same place: `#derive(Eq) struct Q { w: W<S> }` with `S` not `Ord` gives `… which isn't Eq: 'S' isn't Ord (it needs 'impl Ord for S')`. Before, this checked, and `myla run` failed inside the interpreter with `list index -1 out of bounds (len 537)` at `selfhost/interp.my:3964`. A non-generic `#derive(Hash)` was reported at `<myla>/std/hash.my:3:26`.
- As a safety net, any other error in a derived impl's body is moved to its derive, in the program's file (`in_derived`, from `note`).
- Audit of the other derives: `Hash` (generic and not), `Json` and `Toml` on generic types had the same misplaced position (`<myla>/std/hash.my:3:26`, `4:38`, `14:91`). All go through the new check.
- Audit of other diagnostics placed in a std file: a program's `impl Eq for Option<T>` (or `Hash`, or an impl for a std module's derived type such as `json.JsonErrorKind`) was reported at the prelude's or the module's declaration: `<myla>/std/hash.my:2:1`, or `<myla>/std/json.my:36:5`. It is now reported at the program's impl, `type 'Option' derives Eq in the prelude (D182): it can't have an explicit 'impl Eq for Option'` (`record_beside_impl`). The error corpus has no other stderr that points into `lib/std` or `<myla>` except a note that names std.list's place on purpose.
- `not_trait_why` offered `'#derive(Ord)'`, which doesn't exist. It now offers a derive only for `Eq` and `Hash`.

## Proposal (open decision)

Built: **(A)** a derive keeps its rule (each type parameter bounded by the trait alone, MYLA-379). A field that needs more is an error at the derive, whose help gives the impl to write by hand, with every bound the fields lack.

Alternatives:
- **(B)** The derive takes the bounds its fields' impls need, so `P<T>` would be `Eq` where `T: Eq + Ord`. This is Haskell's inferred deriving context. It is convenient, but the bounds of a derived impl would depend on its fields' impls, and the change would be silent.
- **(C)** Bounds written on the derive, such as `#derive(Eq where T: Ord)`. This is new syntax for a rare case that a written impl already covers.

The error is reported at the struct or enum, like the other derive errors (`cannot derive Hash for struct 'Sample': field 'value' …`), not at the field.

## Evidence

- **Failing first**: seven new corpus files, each failing before the change (`python3 -m unittest tests.burn.test_error_corpus.TestErrorCorpus.test_<name>`, 7 failures, positions in `<myla>/std/hash.my`, one with no error at all), each passing after, with its pinned `.stderr`:
  - `type_derive_generic_field_needs_bound` (this task's case)
  - `type_derive_hash_generic_payload_needs_bound`
  - `type_derive_field_argument_not_ord`
  - `type_derive_json_generic_field_needs_bound`
  - `type_derive_toml_generic_payload_needs_bound`
  - `type_impl_beside_prelude_derive`
  - `type_impl_beside_std_derive`
- The help's impls compile and run: `impl<T: Eq + Ord> Eq for P<T>` and `impl<T: json.ToJson + Ord> json.ToJson for Page<T>` print `false`, `true`, `{"items":[1]}`.
- `build/myla test selfhost/checker.my`: 960/960. New cases: `derived_error_at` (the fallback), `std_module_of`, `holds_generic_type`, `has_generic_member`, `derive_lacks`, `check_derived_fields`.
- `tests.burn.test_error_corpus`: 349 tests OK. The bootstrap reaches its fixed point (23,817,887 bytes).
- **Cost** (callgrind, `check`, both CLIs built by `build/myla build` from 35b399e and from this change):
  - hello world: 21,392,922 → 21,400,903 instructions (+0.04%). A first version without the `has_generic_member` filter cost +0.22%.
  - a program that imports std.json and std.toml and derives all four traits on a generic struct: 76,990,041 → 77,068,390 (+0.10%).
- **Suites**: `scripts/test.sh fast` OK (862 tests, 3 skipped); `scripts/test.sh` (full, with test_std_modules, test_compiler_parity, test_lsp, test_embedded_std) OK: 1538 tests, 341 skipped.

## Found on the way

- [[MYLA-538]]: an impl's bound that names a generic trait (`I: Iterator<int>`) isn't checked where the impl is used. `W<int> == W<int>` checks, then fails inside the interpreter.

## Review 2026-11-12

Signed off in [[Project/Review-2026-11-12]].
