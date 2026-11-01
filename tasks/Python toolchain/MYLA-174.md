---
id: MYLA-174
title: The Python backend can't compile a map literal whose values involve generics
type: bug
status: review
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

- [x] A `tuple` branch in `_rewrite_child`
- [x] Parity programs with `[1: Some(2)]` and a generic struct value in `test_compiler_parity.py`
- [x] The monomorphizer's own re-check failures reported as internal compiler errors, not as the user's type errors

## Evidence

- Before: the parity program `map_literal_with_generic_values` failed with `KeyError: 'Option'`; after: it passes (the Python backend prints what the interpreter does). A failure of the monomorphizer (its re-check included) is now `build error: internal compiler error: …`.
- Unit 622, integration 2, burn 826 (5 skipped) and the extension's 54 tests pass on commit 12f6e94; the bootstrap reaches its byte-identical fixed point (6,153,392 bytes).
