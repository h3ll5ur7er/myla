---
id: MYLA-21
title: Destructuring a tuple of boxed recursive enums is miscompiled
type: bug
status: review
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

## Fix

`gen_destruct` in [[selfhost/codegen.my]] now dereferences a boxed leaf's pointer before copying it, and does what the Python backend's `_gen_destruct` does: retains each leaf, registers it as an owner and releases the initializer's temporaries (the last three were missing too; harmless only while the runtime never frees, [[MYLA-22]]).

The new parity test also found a bug in the **Python** backend: a list, map or builder leaf (a plain heap pointer) was copied without a retain, then the initializer's temporaries were released, so `let (v, n) = (i, [i, i])` left `n` pointing at a freed list (and dropped it again at scope end), and `let ((c, xs), s) = nested()` read `len(xs)` as 0. Fixed in [[src/myla/compiler/codegen_x86.py]] (`_gen_destruct`).

- [x] `gen_destruct` dereferences boxed leaves (and retains them)
- [x] The repro prints `5`, and `examples/methods.my`, `traits.my`, `generic_traits.my` and `playground.my` run correctly under the stage3-built `myla` CLI (all four exited 1 before)
- [x] Test first: `destructure_boxed_enum_and_list_leaves` in `tests/burn/test_compiler_parity.py` (failed natively with the Python backend: `0` and a garbage length) and through the self-hosted compiler in `test_selfhost_codegen.py` (failed)
- [x] Burn suite green (336 tests); bootstrap fixed point holds (4,494,795 bytes)
