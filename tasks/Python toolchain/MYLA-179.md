---
id: MYLA-179
title: Map iteration order differs between the interpreter and native code
type: improvement
status: done
priority: low
labels: [maps, parity, design]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). `for k in m` and `keys(m)` visit keys in insertion order in the Python interpreter (a `dict`) and in hash order natively. [[Language/Collections-and-strings]] says the order is undefined, so it isn't a bug by the page, but it is the one place where "the interpreter is the semantics" is false, and a `#test` can't pin a map's keys. Needs a decision: define insertion order (an order vector in the native map cell, in both backends and the self-hosted interpreter), or sort the keys in `keys` and `for`.


Part of the language ergonomics round ([[MYLA-215]]).

## Options

- **A. Undefined, as documented.** Nothing changes; `#test` cases can't show a map's keys and the interpreters and native code keep disagreeing.
- **B. Insertion order** in all four implementations: an order vector in the native map cell (removal leaves a tombstone or compacts). Matches Python's `dict`, so the oracle needs no change; deterministic output.
- **C. Sorted order** for `keys` and `for`: needs an ordering on every key type, and costs a sort per iteration.

## Recommendation

**B.** Deterministic and testable, the cheapest for the oracle, and what users of Python and Swift's ordered collections expect.

## Decision

**D105 (2026-11-01): insertion order** (option B), in every implementation (after [[MYLA-219]], the self-hosted interpreter and the native map).

- [x] A decision on [[Project/Decisions]] (D105)
- [x] Then the implementation in all four implementations with a parity program (two since [[MYLA-219]]: the self-hosted interpreter already kept insertion order; native code now does)

## Evidence

- **How.** The self-hosted interpreter's maps were already parallel lists in insertion order. A removed key's entry is dropped and a re-inserted key goes to the end, as D105 says.
  - Native maps keep their open-addressing table; each slot gains a rank word at its end: `[state][key][value][rank]` ([[selfhost/codegen.my]]).
  - A new key's rank is the count. The rebuild that every removal already does moves the later ranks up, and a grow copies them. So the ranks are always 0 … count − 1, and `__map_keys` (which `for k in m` uses too) writes each key at its rank: no sort and no extra pass.
  - The DWARF description of a slot gains an `order` field, and the gdb pretty-printer shows a map in insertion order.
- **Test first.** `tests/burn/test_map_order.py`: 300 keys inserted out of order through several grows, a value replaced, three keys removed and one inserted again, string keys with list values, a copy changed on its own. It expects Python's `dict` order. The interpreter passed before the change; native code failed (hash order). Both pass after.
- **Cost.** A `[int: int]` slot grows from 24 to 32 bytes. Best of five, a million keys, before → after:
  - insert: 0.164 → 0.197 s (+21 %)
  - lookup: 0.283 → 0.303 s (+7 %)
  - iterate: 0.208 → 0.236 s (+13 %)
  - 4,000 removals from 20,000 keys: 1.451 → 1.670 s (+15 %)
  - The whole map benchmark's peak memory: 98 → 133 MB.
- **An older problem the numbers show.** Every removal rebuilds the whole table, which is O(capacity) per `remove`. A layout like Python's (a dense array of entries in insertion order plus a hash index) would fix that and make iteration cheaper; that would be a task of its own.
- **Docs.** [[Language/Collections-and-strings]], [[Language/Statements]] and [[Architecture/Native-backend]] are updated; the entry on [[Project/Known-issues]] is gone. The burn suite passes (847 tests) and the bootstrap reaches its fixed point with the new seed.

