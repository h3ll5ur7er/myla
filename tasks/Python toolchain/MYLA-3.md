---
id: MYLA-3
title: Compiler crashes assigning a heap-owning struct to a field
type: bug
status: done
priority: high
labels: [native-backend, crash]
---
## Steps to reproduce

```myla
struct Inner { xs: [int] }
struct Outer { inner: Inner }
fun main() {
    var o = Outer { inner: Inner { xs: [1] } }
    o.inner = Inner { xs: [2, 3] }
    print(len(o.inner.xs))
}
```

`python3 myla.py build repro.my`

## Expected

Builds and prints `2`, like `myla run`.

## Actual

`NotImplementedError: reference-counted aggregate assignment is only supported for simple variables`, as an uncaught Python traceback.

## What else turned up

- **Field writes through shared containers broke value semantics.** `_addr_of_lvalue` took the address of `b[0]` without unsharing the list, so after `var b = a`, `b[0].x = 5` changed `a[0].x` too (also for map values, nested fields and list-valued fields). The self-hosted backend did the same.
- **`p = p` was a use-after-free** for a struct holding a list: the old value was released before the new one (the same value) was copied and retained. The native binary printed `0` instead of `3`.

## Fix

[[src/myla/compiler/codegen_x86.py]] and [[selfhost/codegen.my]]: every assignment of a heap-owning type goes through the staged store from [[MYLA-4]] (take the new value with its references, compute the place, release the old value, move the new one in), and every assignment computes its place with `_mut_place_addr` (formerly `_mut_addr_of_struct`), which unshares each list and map on the path. `_addr_of_lvalue` (and the self-hosted `addr_of_lvalue` and unused `mut_holder_addr`) are gone. A variable holds a boxed enum inline, a field or element holds it as a pointer: the staging helpers take an `inline` flag for that.

- [x] Assignment of a heap-owning aggregate to any place (`a.b`, `a.b.c`, `xs[i].f`, `m[k].f`) builds the new value, drops the old one at the computed address, copies and retains
- [x] Parity tests, seen failing first: `assign_heap_owning_struct_to_any_place` and `assign_heap_owning_struct_to_itself` (compiler crash), `assign_to_a_field_of_a_shared_element_copies_it` (printed `5 5 2 7 9 9` instead of `1 5 1 1 1 9`); the same programs through the self-hosted compiler in `test_selfhost_codegen.py`
- [x] No `NotImplementedError` left in the code generator
- [x] Burn suite green (333 tests); bootstrap fixed point holds (4,467,756 bytes)

`a.0 = v` (tuple fields) isn't assignable in the language, so there is nothing to test there.
