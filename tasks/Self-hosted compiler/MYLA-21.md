---
id: MYLA-21
title: Destructuring a tuple of boxed recursive enums is miscompiled
type: bug
status: todo
priority: high
labels: [selfhost, codegen]
---
`gen_destruct` / `collect_leaves` in [[selfhost/codegen.my]] copy `size(T)` bytes straight from an element's slot. For a boxed (recursive) enum the slot holds an 8-byte pointer and must be dereferenced first. The Python backend does this ([[src/myla/compiler/codegen_x86.py#L1954-L1958]]).

## Steps to reproduce

```myla
enum V { VI(int), VP(V), VU }
fun pair() -> (V, int) { return (V.VI(5), 1) }
fun show(v: V) -> int {
    return match v {
        VI(n) => n
        VP(_) => 0
        VU => 0
    }
}
fun main() {
    let (a, b) = pair()
    print(show(a))
}
```

Build with the self-hosted compiler (`build/stage3 repro.my src/myla > r.s`, assemble, link).

## Actual

The program exits 1 (the match falls through to `__trap`). `pair().0` works.

## Impact

This breaks the self-hosted `myla run` (the CLI from `selfhost/main.my`): `let (rv, fs) = self.call_method(...)` in [[selfhost/interp.my]] destructures the recursive `Value`, so `methods.my`, `traits.my`, `generic_traits.my` and `playground.my` fail under it.

## Done when

- [ ] `gen_destruct` dereferences boxed leaves (and retains them)
- [ ] The repro and `examples/methods.my` run correctly under the stage3-built `myla`
- [ ] A selfhost codegen differential test covers destructuring
