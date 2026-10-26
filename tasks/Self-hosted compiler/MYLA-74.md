---
id: MYLA-74
title: Self-hosted interpreter copies containers on every update
type: improvement
status: backlog
priority: low
labels: [selfhost, interpreter, performance]
---
Split out of [[MYLA-32]]. [[selfhost/interp.my]] represents lists, maps, structs and scopes as immutable `Value`s, so every update rebuilds the container (`set_index`, `list_push`, `write_steps`) and each scope lookup copies a frame: an assignment or `push` costs O(n), and a loop that grows a list is quadratic.

## Measurement

Appending `n` integers with `push` in a loop (`myla run`, Python interpreter vs the natively built self-hosted interpreter):

| n | Python | self-hosted |
| --- | --- | --- |
| 5,000 | 0.15 s | 0.23 s |
| 10,000 | 0.16 s | 3.8 s |
| 20,000 | 0.18 s | 5.7 s |

## Ideas

- Keep containers in a store indexed by handle (a list of cells the interpreter owns), so a value holds a handle and an update writes the cell in place; copy-on-write by reference count where value semantics require a copy.
- Or wait for an IR-based backend ([[MYLA-67]]) and interpret that.

## Done when

- [ ] `push` and element assignment are amortised O(1)
- [ ] The interpreter gate still passes, and the table above is measured again
