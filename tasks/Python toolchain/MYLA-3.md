---
id: MYLA-3
title: Compiler crashes assigning a heap-owning struct to a field
type: bug
status: todo
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

## Cause

![[src/myla/compiler/codegen_x86.py#L1159-L1163]]

## Done when

- [ ] Assignment of a heap-owning aggregate to any place (`a.b`, `a.b.c`, `xs[i]`, `m[k].f`) builds the new value, drops the old one at the computed address, copies and retains
- [ ] Parity tests for field, nested field and element targets
- [ ] No `NotImplementedError` left in the code generator
