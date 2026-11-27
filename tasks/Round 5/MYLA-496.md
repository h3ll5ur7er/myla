---
id: MYLA-496
title: "A `for` over a map lists all its keys first, so leaving the loop early still costs the map's size"
type: improvement
status: done
priority: low
labels: [maps, performance, runtime, round-5]
---
Found by [[MYLA-429]]. `for k in m` makes the list of the map's keys before its first step (native code: std.rt's `map_keys`, which walks every slot and, when the ranks have gaps, a block of the ranks; the interpreter: `map_keys_of`, which copies the entries without the holes). So a loop that leaves at its first key, the way to take a map's oldest key, costs the map's size, and a queue drained that way is quadratic in its live keys, even since MYLA-429 made the walk cost the live keys rather than the capacity:

```myla
fun main() {
    var m: [int: int] = [:]
    for i in 0..20000 { m[i] = i }
    var taken = 0
    while m.len() > 0 {
        var first = -1
        for k in m {
            first = k
            break
        }
        m.remove(first)
        taken += 1
    }
    print(taken)
}
```

Natively: 2.8 s for 20,000 keys (x86-64, 2026-11-11), where a dict in insertion order (Python's, or the C of `benchmarks/map_remove`) takes milliseconds.

- [x] Choose: a `for` that walks the retained cell by rank as it goes (the loop holds a reference, so the cell doesn't change under it; a cursor of the next rank and a way to find the slot of a rank without the block of ranks, e.g. the ranks dense once compacted), or a method that gives the oldest key (`first_key() -> Option<K>`), or both
- [x] The queue above linear in its keys natively and interpreted, on every target, D105's order unchanged

## Decision (proposal)

Built: a `for` that walks the cell it holds by rank as it goes, natively and interpreted; no `first_key()`. `for k in m { first = k; break }` costs the gaps since the last loop, so a method would add nothing but a name, and none is needed for the queue.

- **Native** (`lib/std/rt.my`, `selfhost/lower.my`): the map's cell gains, after the next rank, `first` (every rank below it a gap) and the order (`[order:4 × cap]`, the slot index at each rank, written by `map_set_slot` and `map_place_h` as a key takes its rank). A rank is a key's while the slot the order names is full and has that rank, so a removal still only marks a tombstone (no change in the IR of `remove`), and a tombstone taken again by another key, with a rank of its own, is no false hit. `for k in m` (`for_map`) holds the map (retained unless a fixed place, as a list's loop), and steps by std.rt's `map_walk(cell, slot_size, after)`: from `first` on the way in, which it moves past the gaps it finds (a removal only makes gaps, and a compaction starts a new cell at 0), then from the slot after's rank. `keys()` and the compactions go by the order too, so `map_by_rank`'s block of the ranks is gone.
- **Interpreter** (`selfhost/interp.my`, lane A's file, 20 lines): `MapV.lo`, the first place that may hold a key, moved on by a removal of the place it names and reset by a compaction; `exec_for` walks a map's places from it, skipping holes, without `map_keys_of`'s copy.
- Cost: 4 bytes a slot more (an `[int: int]` map's slot is 32 bytes: 12.5 %), an extra store per insert.
- Alternatives: a `first_key() -> Option<K>` method (needs the same `first` and order to be O(1), and leaves `for … break` quadratic); a doubly linked list through the slots instead of ranks (O(1) per step whatever was removed, no extra memory, but every removal unlinks, so `remove` costs more and becomes a call); the ranks dense once compacted (still no slot for a rank without a block of the ranks).

## Evidence

Test first, before (round 5's compiler, `bccc624` plus MYLA-441) and after, x86-64:

| | before | after |
|---|---:|---:|
| the queue above, native (20,000 keys) | 2.59 s | 0.003 s |
| the queue above, interpreted (20,000 keys) | 9.66 s | 0.19 s |
| map_cliff's queue, native (20,000 keys) | 2,647 ms | 0 ms |
| the queue, aarch64 under qemu (20,000 keys) | 35.9 s | 0.035 s |
| the queue, wasm32 under Node (20,000 keys) | — | 0.043 s |
| `_QUEUE` of test_map_remove, native, 5,000 → 20,000 keys | 80 → 2,420 ms (30×) | 0.12 → 0.88 ms |
| `_QUEUE`, interpreted, 2,000 → 8,000 keys | 123 → 1,429 ms (11.6×) | 14 → 53 ms (3.7×) |

- New tests: `test_a_loop_that_leaves_at_the_first_key_costs_what_it_walked_natively` and `…_in_the_interpreter` in `tests/burn/test_map_remove.py` (four times the keys within eight times the time; before, 30× and 11.6×); the parity program `for_over_a_map_walks_its_slots` (a queue with reinsertions, a body that removes and inserts while the loop walks the keys it began with, tombstones taken by new keys, `continue`, `break`, `return` from inside, nested loops over one map, string, `uint8`, struct, list and tuple keys, a `let` map, a field's and a list's map, an emptied map, an async function's loop): the interpreter, the native code before and after all print the pinned output, on x86-64, aarch64 and wasm32.
- A stress of 200,000 rounds of loops with `break`, `continue`, `return` and a body that changes the map, string keys and list values: the same output, 11,292 KB peak before and after (nothing leaks); also with `-g` and `--checked`.
- Callgrind, Myla's instructions: `map_remove` (4,000) 15.78 → 15.90 M (+0.7 %: the order's store per insert, the compactions walking it instead of the slots; `map_by_rank` and its `zero_bytes` gone); `word_freq` (100,000) 140.47 → 140.58 M (+0.08 %); the compiler compiling itself 12,189.6 → 12,194.9 M (+0.04 %). The same outputs.
- Bootstrap fixed point: byte-identical (21,145,493 bytes).

## Review 2026-11-12

Signed off in [[Project/Review-2026-11-12]], with a follow-up in [[MYLA-554]]: the docs don't say what a `for` over a list or map sees when its body changes it (the loop walks what it began with).
