---
id: MYLA-413
title: "An imported std module's bodies parsed and checked once called"
type: improvement
status: in-progress
priority: medium
labels: [loader, checker, performance, check-time]
---
Found by [[MYLA-359]]. Only the implicit modules' function bodies are parsed and checked once called (D164's modules; the owner's decision on [[MYLA-359]]). A program that imports a module of `std` parses and checks all of it and of what it imports: a hello world with `from std.io import println` checks in 100.0 M instructions where one without the import takes 39.4 M, 30 M of it parsing std.io and its imports eagerly and 22 M checking their bodies.

The mechanism is there: the loader's `Loader.lazy` (which files are parsed with `parse_source_lazy`) and the checker's `lazy_decls` (which declarations wait for `called`) would take every module of `std` that isn't the entry. It is a decision, as the implicit modules' was: a type or syntax error in a body of an imported std module that the program doesn't call would show only in that module's own `myla test`, as it now does for the implicit modules.

- [x] Decide: every non-entry module of the standard library, or also a program's own imported modules (whose authors don't run their own `myla test` on each) — D179 (2) and (3): the standard library's only, never a program's own modules
- [x] Build it, with the loader's and the checker's sets widened, and measured as [[MYLA-359]] was (in [[MYLA-432]], after the list of the functions the back ends name and `IoError` in std.ioerror; the evidence is there)

## Review 2026-11-12

Reopened ([[Project/Review-2026-11-12]]): laziness is decided by the module's id, not by where its file is. The rest holds: the guards for unread bodies were proven with mutant compilers, and 399 programs in five configurations build byte-identical code lazily and eagerly, apart from [[MYLA-552]]'s vote. The task also has no evidence section of its own (it points to [[MYLA-432]]).

- [ ] **A program's own top-level `std/` directory is read lazily** (D179: a program's own modules are always read whole): with `from .std.helper import ok` and a `std/helper.my` that holds a type error and a parse error in functions `main` doesn't call, `myla check main.my` says `ok` (`repro-r5/parser/own/`; the same tree with the directory named `other/` reports both, `own3/`). `Loader.lazy_std` and `in_std` test the `std$` prefix of the module id; decide by the file's root
- [ ] An evidence section here
