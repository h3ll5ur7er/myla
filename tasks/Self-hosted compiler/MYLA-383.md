---
id: MYLA-383
title: "Diagnostics: a list where an iterator is expected, and module functions' mangled names"
type: improvement
status: todo
priority: low
labels: [checker, diagnostics]
---
Found by the `std.iter` lane ([[MYLA-381]]).

- [ ] A list passed where an `I: Iterator<T>` is expected (`xs |> iter.map((x) => x * 3)`, `iter.count(xs)`) gives "cannot infer the type of lambda parameter 'x'" or "cannot infer type parameter(s) T". The bound's failure should come first, with a hint: "'[int32]' is not an Iterator: write 'xs.iter()'". With an annotated lambda it is already "does not satisfy the bound 'I: Iterator<int32>'".
- [ ] A module function's name shows mangled in messages: "function 'std$iter$sum' expects 2 argument(s)", "required by 'std$iter$map'", `deque.of([1], 2)`'s `std$deque$of` (also noted on [[MYLA-330]]). They should read `iter.sum`, as the call is written
- [ ] Each in the error corpus with its pinned `.stderr`
