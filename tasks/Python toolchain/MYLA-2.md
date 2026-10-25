---
id: MYLA-2
title: "Native code keeps a dangling pointer when a match binding's list grows"
type: bug
status: todo
priority: high
labels: [native-backend, memory, parity]
---
A `match` binding that holds a list (or anything with a heap cell) borrows the scrutinee's cell without taking a reference. If the arm body then mutates the original variable, the cell is changed in place, or grown and freed, under the binding.

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

The native binary prints `0`: `ys` points at a freed cell whose first word now holds the free-list link.

## Cause

`_gen_match` copies the scrutinee into a frame slot and `_match_pat` copies binding values without `_retain` ([[src/myla/compiler/codegen_x86.py#L1993-L2055]]). The comment says bindings "borrow from the scrutinee, which outlives the match", but nothing stops the arm from writing to the variable the scrutinee came from. `for … in` avoids the same problem by retaining the list for the loop ([[src/myla/compiler/codegen_x86.py#L1296-L1298]]).

## Done when

- [ ] The match scrutinee copy holds a reference (retained after the copy, dropped after the match), so a write in an arm copies-on-write
- [ ] The repro above is in `tests/burn/test_compiler_parity.py` (also with a struct holding a list, and a map)
- [ ] Arena-reclaim stress still passes (no new leak)
