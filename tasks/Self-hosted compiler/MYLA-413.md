---
id: MYLA-413
title: "An imported std module's bodies parsed and checked once called"
type: improvement
status: review
priority: medium
labels: [loader, checker, performance, check-time]
---
Found by [[MYLA-359]]. Only the implicit modules' function bodies are parsed and checked once called (D164's modules; the owner's decision on [[MYLA-359]]). A program that imports a module of `std` parses and checks all of it and of what it imports: a hello world with `from std.io import println` checks in 100.0 M instructions where one without the import takes 39.4 M, 30 M of it parsing std.io and its imports eagerly and 22 M checking their bodies.

The mechanism is there: the loader's `Loader.lazy` (which files are parsed with `parse_source_lazy`) and the checker's `lazy_decls` (which declarations wait for `called`) would take every module of `std` that isn't the entry. It is a decision, as the implicit modules' was: a type or syntax error in a body of an imported std module that the program doesn't call would show only in that module's own `myla test`, as it now does for the implicit modules.

- [x] Decide: every non-entry module of the standard library, or also a program's own imported modules (whose authors don't run their own `myla test` on each) — D179 (2) and (3): the standard library's only, never a program's own modules
- [x] Build it, with the loader's and the checker's sets widened, and measured as [[MYLA-359]] was (in [[MYLA-432]], after the list of the functions the back ends name and `IoError` in std.ioerror; the evidence is there)

## Review 2026-11-12

Reopened ([[Project/Review-2026-11-12]]): laziness is decided by the module's id, not by where its file is. The rest holds: the guards for unread bodies were proven with mutant compilers, and 399 programs in five configurations build byte-identical code lazily and eagerly, apart from [[MYLA-552]]'s vote. The task also has no evidence section of its own (it points to [[MYLA-432]]).

- [x] **A program's own top-level `std/` directory is read lazily** (D179: a program's own modules are always read whole): with `from .std.helper import ok` and a `std/helper.my` that holds a type error and a parse error in functions `main` doesn't call, `myla check main.my` says `ok` (`repro-r5/parser/own/`; the same tree with the directory named `other/` reports both, `own3/`). `Loader.lazy_std` and `in_std` test the `std$` prefix of the module id; decide by the file's root
- [x] An evidence section here

## Evidence

Round 6, wave 2 (base `07445ab`), commit "MYLA-413: a program's own std/ directory is read whole". `Loader.in_std_root` (`selfhost/loader.my`) decides by the file's root, as `module_id` names it: a file under the stdlib root's `std/` or the carried library's. `lazy_std` and the merge's `in_std` (which records a module's impls and lazy functions in `std_impls`) use it instead of the `std$` prefix of the module id, which a program's own `std/helper.my` has too (`std$helper`); the entry stays out of `std_impls` as before.

- Test first: `tests.burn.test_lazy_std.ImportedStdBodies.test_a_programs_own_std_directory_is_read_whole`, the review's `parser/own/` and `own3/` for a type error and a parse error, `check` and `run`: failed before for `std/` (`ok`, twice), passes after; `other/` passed before and after. `lazy_std`'s and `in_std_root`'s cases in the loader (a program's own `std/`, no stdlib root, the carried library, a project inside the stdlib root).
- The review's reproducer: `myla check main.my` in `own/` was `ok`; it is now `parse error: expected variable name, found '='` at `std/helper.my:8:9`, as `own3/` gives at `other/helper.my:8:9`.
- Check time (callgrind, `MYLA_THREADS=1`, `myla check`, the carried library): a hello world 20,642,824 → 20,668,611 instructions (+0.12 %), `import std.http` (`http.reason`) 146,627,013 → 146,741,100 (+0.08 %).
- `scripts/bootstrap.sh`: byte-identical fixed point, `selfhost/embedded_std.my` unchanged.
- Found on the way: the checker still takes a function named `std$…` for the library's, so such a module may call raw-memory primitives ([[MYLA-584]], the checker's lane).
