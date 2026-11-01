---
id: MYLA-9
title: Generic instantiations can get the same mangled name
type: bug
status: done
priority: low
labels: [monomorphize, native-backend]
---
## Steps to reproduce

```myla
struct A_B { v: int }
struct C { v: int }
struct A { v: int }
struct B_C { v: int }
struct Pair<X, Y> { x: X, y: Y }
fun first<X, Y>(p: Pair<X, Y>) -> int { return 1 }
fun main() {
    let p1 = Pair { x: A_B { v: 1 }, y: C { v: 2 } }
    let p2 = Pair { x: A { v: 3 }, y: B_C { v: 4 } }
    print(first(p1) + first(p2))
}
```

## Actual

`myla run` prints `2`; `myla build` fails with `type error: duplicate top-level declaration 'Pair__A_B_C'`. For functions the collision is silent: the second specialization is skipped (`if mangled in self.emitted_fns: continue`).

## Cause

`_mangle` joins type tokens with `_`, which also appears in names ([[src/myla/compiler/monomorphize.py#L393-L417]]).

## Done when

- [x] Mangling is injective (length-prefixed tokens, or a separator that can't appear in identifiers such as `$`, which the loader already uses)
- [x] The repro is a parity test
- [x] Check [[selfhost/codegen.my]] `mono_token` too, which also maps every function type to `X` (see [[MYLA-33]])

## How

Every type-argument token is prefixed with its length, and every built-in token starts with `.` (which identifiers can't contain), so the name is injective: `Pair<A_B, C>` → `Pair__3A_B1C`, `Pair<A, B_C>` → `Pair__1A3B_C` ([[Architecture/Monomorphization]]). The same `type_token` names the code generator's per-type helpers (`__drop_map_…` had the same ambiguity: `[A: B_C]` and `[A_B: C]` shared a helper). The self-hosted code generator uses the same scheme in `mono_token` / `map_token` ([[selfhost/codegen.my]]), now with a real token for function types instead of `X` ([[MYLA-33]]).

## Evidence

- Parity program `generic_instantiations_get_distinct_names` (the repro with different layouts behind the colliding names, generic functions over two function types and over tuples) in [[tests/burn/test_compiler_parity.py]] and the self-hosted `PARITY_PROGRAMS`. Before: the Python backend failed with `duplicate top-level declaration 'Pair__A_B_C'`, and the self-hosted binary silently reused one instantiation and printed `1` instead of `4`. After: both print `4 42 4 int to int str to str 11`, like the interpreter.
- gdb still breaks on a generic instance by its label: `break 'myla_first__6.int32'` ([[Development/Debugging]]).
