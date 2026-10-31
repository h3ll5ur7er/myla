---
id: MYLA-174
title: The Python backend can't compile a map literal whose values involve generics
type: bug
status: todo
priority: high
labels: [compiler, monomorphization]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]).

```myla
fun main() {
    let m = [1: Some(2)]
    print(len(m))
}
```

`python3 myla.py run` prints 1 and the self-hosted compiler builds it; `python3 myla.py build` dies with `KeyError: 'Option'` from the monomorphizer's re-check ([[src/myla/compiler/monomorphize.py]]). With `let m: [int: Box<str>] = [1: Box { v: "one" }]` it reports `type error: unknown struct 'Box'` against a correct line. `_rewrite_child` descends into `Node` and `list` but not `tuple`, and `MapLit.entries` is a list of `(key, value)` tuples; the checker's `_desugar_value` and the interpreter's `_names_in` both handle tuples.

- [ ] A `tuple` branch in `_rewrite_child`
- [ ] Parity programs with `[1: Some(2)]` and a generic struct value in `test_compiler_parity.py`
- [ ] The monomorphizer's own re-check failures reported as internal compiler errors, not as the user's type errors
