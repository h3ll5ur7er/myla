---
id: MYLA-143
title: A var self method on a shared list element writes the shared list
type: bug
status: done
priority: high
labels: [codegen, selfhost, python-toolchain, memory]
---
Found while doing [[MYLA-142]]: in both native backends, a method writing its receiver (`var self`) called on a list element or a field of one (`cs[1].bump(10)`, `b.rows[0].bump(1)`) got the receiver's address by reading the place, without making the lists on the way unshared. A copy of the list taken before (`let copy = cs`) then saw the method's writes, where the interpreters keep it as it was (Myla's value semantics, D38).

```myla
var cs = [C { n: 0 }]
let copy = cs
let e = cs[0].bump(1000)
print(copy[0].n)          // the interpreters: 0; both backends printed 1000
```

- [x] The self-hosted backend: the receiver of a `var self` method that is a place of a variable is passed as `place` gives it, which unshares every list on the way (`direct_call` in `lower.my`)
- [x] The Python backend: such a receiver is a `("place", …)` argument, its address from `_mut_place_addr` (`_arg_kind` in `codegen_x86.py`)
- [x] A parity program for both backends

## Evidence

- `var_self_method_on_a_shared_element_copies_it` (`tests/burn/test_compiler_parity.py`, and in the self-hosted backend's `PARITY_PROGRAMS`): an element, an element of a field, an element of a nested list, each with a copy of the list kept; both backends print what the interpreter prints. It fails on the Python backend without the fix.
