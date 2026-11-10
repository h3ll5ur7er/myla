---
id: MYLA-413
title: "An imported std module's bodies parsed and checked once called"
type: improvement
status: backlog
priority: medium
labels: [loader, checker, performance, check-time]
---
Found by [[MYLA-359]]. Only the implicit modules' function bodies are parsed and checked once called (D164's modules; the owner's decision on [[MYLA-359]]). A program that imports a module of `std` parses and checks all of it and of what it imports: a hello world with `from std.io import println` checks in 100.0 M instructions where one without the import takes 39.4 M, 30 M of it parsing std.io and its imports eagerly and 22 M checking their bodies.

The mechanism is there: the loader's `Loader.lazy` (which files are parsed with `parse_source_lazy`) and the checker's `lazy_decls` (which declarations wait for `called`) would take every module of `std` that isn't the entry. It is a decision, as the implicit modules' was: a type or syntax error in a body of an imported std module that the program doesn't call would show only in that module's own `myla test`, as it now does for the implicit modules.

- [ ] Decide: every non-entry module of the standard library, or also a program's own imported modules (whose authors don't run their own `myla test` on each)
- [ ] Build it, with the loader's and the checker's sets widened, and measured as [[MYLA-359]] was
