---
id: MYLA-110
title: Keep checking after a declaration-level type error
type: improvement
status: review
priority: low
labels: [diagnostics, checker]
---
Since D80 ([[MYLA-65]]) both checkers check every function's attributes and body on their own, but an error while building the tables (names, aliases, struct fields, signatures, traits, impls, bounds, constants) still ends the check: a duplicate declaration or an unknown type in a signature is the only error reported, even when bodies elsewhere have errors of their own.

Going on needs an error type: a declaration whose part failed stays defined, with that part's type as an error type that every check accepts silently, so later errors that only follow from the first one don't appear (an unknown type in a parameter must not also give a mismatch at every call).

- [x] An error type in `types.py` and `selfhost/checker.my` (`Type.TError`), accepted by unification, operators, calls, fields and patterns without a message: a body's check ends silently where it depends on it, instead of every check accepting it (D84)
- [x] Record the table phases' errors per declaration (`_collect_globals` … `_fold_consts`), the failed part becoming the error type
- [x] The checker gate and the error corpus with files whose errors span declarations and bodies
- [x] Keep the first error of a run where it is (the gates and editors rely on it), unless it followed from a declaration error found later

## How

Details: [[Architecture/Type-checker]], "Going on after a declaration's error"; D84.

- **The error type:** `ErrorType`/`ERROR` and `_has_error` in [[src/myla/types.py]]; `Type.TError`, `has_error`, `sig_has_error` in [[selfhost/checker.my]]. It is written `{error}`, which no message shows.
- **Declaration phases:** every phase records each part's error and goes on (`_part`, `_record`, `_fail_part`; self-hosted `record`, `resolve_part`, `param_part`, `record_result`, which return `stopped()` at the limit). A failed type becomes the error type; a declaration, field, variant, method or impl that can't be added is left out (`_skipped`, by position in the program, since the self-hosted prelude's node ids repeat the program's); a failed derive or non-conforming impl breaks its (trait, type) pair (`_broken_impls`); an impl for a type that failed loses its methods' and trait's names (`_lost_methods`, `_lost_traits`); a bad bound is dropped and its function's body skipped; a failed alias is cached as the error type, so it is reported once; a failed const keeps its declared type and no value. `_collect_globals` became `_collect_one` per declaration, `_resolve_impls` `_resolve_impl` and `_check_impl_target`; the trait conformance check says whether it could compare every method.
- **Bodies:** `_infer` wraps `_infer_node`, `_check_lvalue` and `_check_pattern` likewise, and end the check (`_Poisoned`; self-hosted `poisoned()`, carried by `?` and dropped by `note`) where a type contains the error type. So do generic calls and partial applications of a signature with it, `?` under a failed return type, a broken pair or lost trait (`_type_implements`), a lost method, a redefined builtin. A parameter, field, payload or return type of the error type skips the argument or value instead, a `let` annotated with a failed alias binds the error type, and a call statement may have it.
- The derive that relies on an `impl Eq` for a type that doesn't exist is left broken without an error: that error followed from the impl's, which the impl phase reports later.

## Evidence

Before, the first line only; now the whole file is checked:

```
type error: unknown type 'Nope'
  --> examples/errors/type_recover_param_types.my:9:10
  |
9 | fun f(x: Nope, n: int) -> int {
  |          ^^^^

type error: unknown type 'Nope'
  --> examples/errors/type_recover_param_types.my:13:10
   |
13 | fun g(x: Nope) -> int {
   |          ^^^^

type error: cannot assign value of type 'bool' to binding of type 'int32'
  --> examples/errors/type_recover_param_types.my:19:5
   |
19 |     let y: int = true
   |     ^^^^^^^^^^^^^^^^^

error: aborting due to 3 previous errors
```

(`g`'s `x + 1` and the calls `f(1, 2)` and `g("s")` say nothing.)

- Tests failing first: the 11 `type_recover_*` corpus files (each reported only its first error) and the unit tests of `test_declaration_recovery.py`.
- The mutant sweep found follow-on errors the first version still gave, each fixed with the rule now in place: a field of a function type that failed made `obj.f(x)` say "no method"; a failed return type made `?` ask for a `Result`; an impl for an unknown type left its methods' calls saying "no method"; and a `#derive(Eq)` relying on such an impl failed first. 674 mutants now report exactly the injected error in both checkers.
- Mutation checks: without the poison in Python's `_infer`, 300 mutants report follow-on errors; without it in the self-hosted `infer`, 320 gate cases fail.
- Unit 575 → 595, integration 2, burn 722 → 735 (5 skipped, as before), extension 54: all pass. Bootstrap fixed point: 6,060,177 bytes.
- Cost: the compiler compiling itself, best of 3, twice: 1.04 and 1.00 s before, 1.05 and 1.00 s after; peak 92 → 94 MB. The Python `myla check selfhost/gen_main.my`: 3.05 s before, 2.73 s after (noise).

