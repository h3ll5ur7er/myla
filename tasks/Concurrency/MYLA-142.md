---
id: MYLA-142
title: Awaited var self methods on list elements
type: feature
status: done
priority: low
labels: [concurrency, codegen, selfhost]
---
After [[MYLA-138]]: in a program with tasks, the self-hosted backend refused an awaited `var self` method of a struct called on a list element (`await xs[i].bump()`): the method runs on a frame of its own with a copy of the receiver, which goes back to the receiver when it ends, and that was done only for a variable or a field of one.

- [x] A receiver that is a list element, at any depth of fields and lists of a variable (not through an actor, whose state may change while the method waits)
- [x] Each index computed once, before the call, into a slot of its own: reading the receiver and writing it back name the same element, and an index with effects runs once
- [x] Written back through the place, each list on the way unshared ([[MYLA-143]])

## Design

Nothing reaches the caller's variable while the method waits: the method works on its copy, other tasks never see the caller's variables, and the caller itself is suspended. So the element is still where it was, and the place can be computed again after the method, from the same indices (`fixed_receiver`, `local_place` in `lower.my`).

## Evidence

- Before: `main can't be lowered to the IR: an awaited 'var self' method on an element`.
- `var_self_on_elements` (`test_concurrency_programs_match_the_interpreter`, natively with and without `--async-frames`): `await cs[1].bump(5)`, `await cs[pick(0)].bump(2)` (`pick` prints once), `await cs[i % 2].bump(1)` in a loop, `await board.rows[0].bump(7)`, and a copy of the list taken before a call keeping its value; it prints what the Python interpreter prints.
- 300,000 rounds of an awaited call on an element holding a growing list of strings, with a copy of the list taken each round: the interpreter's result, 11 MB peak.
