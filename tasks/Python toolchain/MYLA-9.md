---
id: MYLA-9
title: Generic instantiations can get the same mangled name
type: bug
status: backlog
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

- [ ] Mangling is injective (length-prefixed tokens, or a separator that can't appear in identifiers such as `$`, which the loader already uses)
- [ ] The repro is a parity test
- [ ] Check [[selfhost/codegen.my]] `mono_token` too, which also maps every function type to `X` (see [[MYLA-33]])
