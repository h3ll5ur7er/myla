---
id: MYLA-110
title: Keep checking after a declaration-level type error
type: improvement
status: backlog
priority: low
labels: [diagnostics, checker]
---
Since D80 ([[MYLA-65]]) both checkers check every function's attributes and body on their own, but an error while building the tables (names, aliases, struct fields, signatures, traits, impls, bounds, constants) still ends the check: a duplicate declaration or an unknown type in a signature is the only error reported, even when bodies elsewhere have errors of their own.

Going on needs an error type: a declaration whose part failed stays defined, with that part's type as an error type that every check accepts silently, so later errors that only follow from the first one don't appear (an unknown type in a parameter must not also give a mismatch at every call).

- [ ] An error type in `types.py` and `selfhost/checker.my` (`Type.TError`), accepted by unification, operators, calls, fields and patterns without a message
- [ ] Record the table phases' errors per declaration (`_collect_globals` … `_fold_consts`), the failed part becoming the error type
- [ ] The checker gate and the error corpus with files whose errors span declarations and bodies
- [ ] Keep the first error of a run where it is (the gates and editors rely on it)
