---
id: MYLA-2
title: "Native code keeps a dangling pointer when a match binding's list grows"
type: bug
status: done
priority: high
labels: [native-backend, memory, parity]
---
A `match` binding that holds a list (or anything with a heap cell) borrowed the scrutinee's cell without taking a reference. If the arm body then mutated the original variable, the cell was changed in place, or grown and freed, under the binding.

## Steps to reproduce

```myla
fun main() {
    var xs = [1]
    match xs {
        ys => {
            push(xs, 2)
            push(xs, 3)
            push(xs, 4)
            push(xs, 5)
            print(len(ys))
        }
    }
}
```

## Expected

`1` (value semantics; the interpreter prints `1`).

## Actual

The native binary printed `0`: `ys` pointed at a freed cell whose first word held the free-list link. The self-hosted backend printed the wrong length for the same program with a map (`5` instead of `1`): it never frees ([[MYLA-22]]), so only in-place changes showed.

## Fix

[[src/myla/compiler/codegen_x86.py]] (`_gen_match`) and [[selfhost/codegen.my]] (`gen_match`): when an arm may write to the variable the scrutinee comes from, the match's copy of the scrutinee is retained and released after the match (or by an early exit from an arm, through the drop scopes), and the bindings borrow from the copy. A write in the arm then copies on write.

Retaining every scrutinee made the self-hosted compiler 17% larger and its self-compile 14% slower (every `match e.kind` and every `?` paid for it). So the code generators decide statically, and conservatively, whether any arm may write to the scrutinee's root variable (`_may_write` / `arms_may_write`): an assignment to or into it, a mutating builtin on it (`push`, `pop`, `remove`, `append`, `append_byte`), or a method call on it (it may take `var self`). Myla has no references and closures capture by value, so nothing else can. With that, the self-hosted compiler is 0.6% larger than before and compiles itself as fast (1.44 s against 1.43 s, best of 5).

- [x] The match scrutinee copy holds a reference when an arm may write its variable (retained after the copy, dropped after the match), so a write in an arm copies on write
- [x] Test first, seen failing (the native binary trapped): `match_binding_survives_writes_to_the_scrutinee` in `tests/burn/test_compiler_parity.py`, with a list, a struct holding a list, a map and an enum payload, also run through the self-hosted compiler; unit tests for the write analysis in `tests/unit/test_compiler.py::TestMatchScrutineeOwnership`
- [x] Arena-reclaim stress still passes (no new leak); burn suite green (334 tests); bootstrap fixed point holds (4,493,910 bytes)
