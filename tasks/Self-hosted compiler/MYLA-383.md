---
id: MYLA-383
title: "Diagnostics: a list where an iterator is expected, and module functions' mangled names"
type: improvement
status: review
priority: low
labels: [checker, diagnostics]
---
Found by the `std.iter` lane ([[MYLA-381]]).

- [x] A list passed where an `I: Iterator<T>` is expected (`xs |> iter.map((x) => x * 3)`, `iter.count(xs)`) gives "cannot infer the type of lambda parameter 'x'" or "cannot infer type parameter(s) T". The bound's failure should come first, with a hint: "'[int32]' is not an Iterator: write 'xs.iter()'". With an annotated lambda it is already "does not satisfy the bound 'I: Iterator<int32>'".
- [x] A module function's name shows mangled in messages: "function 'std$iter$sum' expects 2 argument(s)", "required by 'std$iter$map'", `deque.of([1], 2)`'s `std$deque$of` (also noted on [[MYLA-330]]). They should read `iter.sum`, as the call is written
- [x] Each in the error corpus with its pinned `.stderr`

## Evidence

- A bound naming a generic trait with its arguments (`I: Iterator<T>`) is held to its trait as soon as an argument fixes its type parameter (`check_generic_bounds`, in `infer_generic_call`), so its failure comes before the lambda's parameter or the type parameter it would have solved; a type with an `iter()` method (a list, a map) gets a help (`iter_hint`). Before, then after:
  - `xs |> iter.map((x) => x * 3)`: "cannot infer the type of lambda parameter 'x'; annotate it (e.g. 'x: int')" → "type '[int32]' does not satisfy the bound 'I: Iterator<T>' required by 'iter.map'" at `xs`, "help: '[int32]' is not an Iterator: write 'xs.iter()'".
  - `iter.count(xs)`: "cannot infer type parameter(s) T for 'std$iter$count' from the arguments; add a type annotation to guide inference" → the same bound failure, by 'iter.count', with the help.
  - with an annotated lambda: "… 'I: Iterator<int32>' required by 'std$iter$map'" at the call → "… 'I: Iterator<T>' required by 'iter.map'" at `xs`, with the help.
- The checker's errors and warnings, and their notes, name a module's functions and types as a program writes them, by the module's last segment, once checking ends (`unmangled`, `unmangled_all` in `run_all`; one place, so every message gets it): "function 'std$iter$sum' expects 2 argument(s)" → "function 'iter.sum' …", "function 'std$deque$of'" → "'deque.of'", "binding of type 'std$deque$Deque<int32>'" → "'deque.Deque<int32>'", "generic function 'std$deque$of' cannot be used as a value" → "'deque.of'". `#test` cases on `unmangled` pin the rule (a `$` that isn't between two names stays).
- Other places a mangled name can reach a message, outside the checker: the lowering's `become` stack-words error names `self.fn_name` ([[selfhost/lower.my]]), qualified for a function of a module other than the entry file's; left, as batch 3 owns that file. The language server's hovers show types through `type_name`, qualified too (not a message).
- In the error corpus, pinned: `type_iter_list_not_iterator`, `type_iter_count_list`, `type_module_function_name`. `tests.burn.test_error_corpus` (296) and `tests.burn.test_selfhost_checker` (6) pass; no oracle line changed.
