---
id: MYLA-110
title: Keep checking after a declaration-level type error
type: improvement
status: in-progress
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

