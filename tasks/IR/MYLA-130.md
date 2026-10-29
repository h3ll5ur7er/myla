---
id: MYLA-130
title: Tail-call follow-ups
type: feature
status: done
priority: low
labels: [ir, codegen, selfhost]
---
What [[MYLA-128]] left for the self-hosted backend, each kept only if it pays:

- [x] A word a tail call passes on in its own place (a parameter in its position, the result's address) is neither pushed nor popped (`emit_tail_call`, `emit_frame_handover`'s `in_place`)
- [x] `moves` hands a slot's reference over when what is taken from it is only read before the drop (`only_reads`) and before the retained value is taken (its taker would share the value at one reference less), a plain scalar read out of it being a copy of its own (`plain_scalar`): `become total(xs, i + 1, acc + xs[i])` no longer retains and releases `xs`
- [x] A partial application's thunk jumps to its function (or through its function value) instead of calling it, so `become` through one doesn't grow the stack either

## Evidence

- The parity program `become_keeps_the_stack_flat` at a million deep runs 347,987,209 instructions instead of 369,987,411 (−6%; −2.2% from the words left in place, −3.9% from the move of `xs`), with and without `-g`, same output; compiling itself, the compiler runs 0.02% more instructions (2,762,898,865 → 2,763,586,247: the longer scan) and emits 1.6 kB less code, at the same fixed point.
- `test_partial_application_thunks_jump`: a `become` through a partial application a million deep, which segfaulted before, runs; `test_become_replaces_the_frame` checks the move and the words left in place.
- A first version let the slot be read after the retained value was taken; three parity programs caught it (`remove_leaves_map_copies_alone`, `assign_to_a_field_of_a_shared_element_copies_it`, `pop_a_boxed_enum`: a copy changed in place through its taker showed through the original).
- Unit 595, integration 2, burn 760 (5 skipped) and the extension's 54 tests pass; the bootstrap reaches its byte-identical fixed point (5,307,333 bytes).
