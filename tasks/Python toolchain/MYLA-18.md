---
id: MYLA-18
title: "Strings from +, format and builders are never freed"
type: improvement
status: done
priority: low
labels: [native-backend, memory]
---
`str` values are not reference-counted: results of `+`, `format`, `build`, `chars` input and `std` I/O live in the arena until the process exits ("arena-resident, by design", D41 note in [[Project/Decisions]]). The arena is 1 GiB, and running out traps silently.

Fine for the compiler; a long-running program that builds strings in a loop eventually dies.

## Done when

- [x] Decide whether `str` joins reference counting (heap strings get a header; literals stay static with a sentinel refcount)
- [x] If yes: retain/drop strings like lists, in both native backends

## How

Decision D62: yes. Heap strings already had the cell header (`__alloc`), so the change is mostly making `str` an owning type, in `codegen_x86.py` and `selfhost/codegen.my` alike:

- `str` joins the cell types (`_CELL_TYPES` / `is_cell_t`), so every existing rule for list pointers applies: locals, fields, elements, captures and returns retain; scope ends, temporaries and container drops release (`__str_drop`, which frees at zero).
- Literals and the renderers' constants (`true`, `false`, `-`, `nan`, …) move from `.rodata` to `.data` as cells with a header and a count of 2^62 (`STATIC_RC`): retains and drops change it but it never reaches zero, so no code needs to tell static strings apart. `__bool_to_str` and `__float_to_str` return such constants as new references (they bump the count), like the heap results.
- New temporaries: `a + b` gets a slot that the statement's end releases. `format` keeps track of which pieces are fresh (rendered numbers, running results) and releases them once concatenated; its result is always a new reference. `print` of a float or char releases the rendered string. `__int_to_str` released no intermediate before.
- Map keys: a map holds a reference to each `str` key. Python backend: `__put_map` retains an inserted key, `grow` and `remove` move keys (giving back the reference put took), and `drop`, `clone`, `keys` and `remove` treat keys like values. Self-hosted: `__map_set_slot` retains a claimed key, `__map_grow` moves keys, `__map_keys` takes an `is_str` flag and retains, `remove` releases the key, and the per-type drop and clone helpers already handled owning keys. `for k in m` in the self-hosted backend registers its key list with a drop scope, so a `return` inside the loop releases it.
- Found on the way, in the self-hosted backend: `remove` left a tombstone and the load factor counted only occupied slots, so after enough distinct keys no slot was empty and a lookup of a missing key looped forever (the compiler at the previous commit hangs on the parity program `remove_many_distinct_keys`). `remove` now rebuilds the table at the same capacity (`__map_rebuild`, sharing `__map_grow`'s body), as the Python backend always did.

Docs: D62 in [[Project/Decisions]], [[Architecture/Native-backend]] (value layout, heap), [[Architecture/Self-hosted-compiler]].

## Evidence

- `STRESS_STR_SRC` (concatenation, `format` with int/bool/char, f-strings, builders, strings in structs and lists, map keys inserted, removed and listed, about 1.4 GB in total): the Python backend runs out of memory without the change and passes in 1.5 s with it; the self-hosted backend passes under the 30 MB peak bound.
- The compiler compiling itself, same output byte for byte: Python-built stage 1 1.74 s / 221 MB → 1.31 s / 84 MB; self-compiled stage 3 2.28 s / 211 MB → 2.14 s / 80 MB.
- Bootstrap fixed point: 7,527,421 bytes (the retain and drop code makes the output 20 % larger).
- Unit 466, integration 4, burn 391: all pass.
