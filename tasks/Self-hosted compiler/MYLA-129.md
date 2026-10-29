---
id: MYLA-129
title: A heap-free aggregate argument read from a `var self` receiver still sees its writes
type: bug
status: done
priority: medium
labels: [codegen, selfhost]
---
Found while making [[MYLA-128]]. [[MYLA-123]] stages an argument read from the receiver's variable of a `var self` method only when its type owns heap memory (`_aliased_args` and the self-hosted `stage` both test `owns_heap`). An aggregate without heap members is still passed as the address it is read from, so the method's writes to its receiver show through it. Both native backends print 5 here, where the interpreters print 1:

```myla
struct P { x: int }
struct W { p: P }
impl W {
    fun m(var self, q: P) -> int {
        self.p.x = 5
        return q.x
    }
}
fun main() {
    var w = W { p: P { x: 1 } }
    print(w.m(w.p))
}
```

`become` rejects any struct, tuple or enum that is a part of `self` passed to the method that changes it (D87), so this only concerns ordinary calls.

- [x] A parity program that fails on both native backends
- [x] Stage every aggregate argument read from the receiver's variable, heap-free ones too (a plain copy, nothing to release), in both backends

## Evidence

- The parity program `heap_free_arguments_survive_the_receivers_writes` (a struct, a tuple, an enum, the receiver itself, a list element's part) printed `55 15 9 6 55 9 23` on both native backends, where the interpreters print `15 7 0 2 25 4 23`; with the fix both print the interpreters' output.
- Unit 595, integration 2, burn 760 (5 skipped) and the extension's 54 tests pass; the bootstrap reaches its byte-identical fixed point.
