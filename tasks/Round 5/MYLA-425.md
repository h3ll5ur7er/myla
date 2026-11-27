---
id: MYLA-425
title: "P11 Numbers and containers: D184 sweep, iterators, error types"
type: bug
status: done
priority: medium
labels: [std, collections, num, overflow, round-5]
---
Work package P11 of [[Project/Review-2026-11-09]] (wave A2), with round 4's additions from [[Project/Review-2026-11-10]]. Files: `lib/std/num.my`, `time.my`, `deque.my`, `set.my`, `heap.my`, `btree.my`, `grid.my`, `bitset.my`, `graph.my`, `encoding.my`, `url.my`'s error type only, `list.my` for one test.

- [x] M18 and D184: `to_hex`/`to_binary` widths ([[MYLA-331]]), `Duration.abs` of the minimum and "arithmetic wraps" ([[MYLA-334]]), `deque.with_capacity` (2^30 + 1 hangs natively, [[MYLA-330]]), `grid.new`; then a sweep of each module for arithmetic on caller-supplied numbers
- [x] `iter()` on Set, Deque, Heap and the B-tree; `==` on Set ([[MYLA-330]])
- [x] D168: `message()` and `Format` on `EncodingError`, `UrlError` and `ParseIntError` ([[MYLA-329]], [[MYLA-405]])
- [x] [[MYLA-342]]'s follow-ups: `row`/`column` out of range behave alike; negative weights refused where a negative cycle would never return
- [x] [[MYLA-323]]'s follow-up: a test for `sort_unstable`'s heapsort fallback in `list.my`

## What changed

- **std.num** ([[lib/std/num.my]], [[Language/Standard-library/Num]]): a negative width of `to_hex`/`to_binary` is a runtime error naming it (`to_hex: width -3 is negative`); a negative `prec` of `format_fixed` too, and its places are counted in `int64` and compared so that a `prec` near `int32`'s maximum can't overflow; `pow2` of `int32`'s minimum is 0 (it negated it); `f64_literal_bits` of a text that isn't a float literal is a runtime error (a `uint8` underflow before). `ParseIntError` has `message()` (`no digits`, `not a digit at byte 1`, `out of range`, the words the page's example used) and `Format`; the page's example uses it. The builtin `format(...)` calls became f-strings (the language server's rule for a std file that declares `format`).
- **std.time** ([[lib/std/time.my]], [[Language/Standard-library/Time]]): `micros` … `hours`, `+`, `-`, `mul_int`, `div_int`, and `Instant`'s `add`, `since`, `elapsed` are runtime errors past a Duration's range in every build (`time.hours: 3000000 is past a Duration's range (about 292 years)`), through std.int's `checked_*`; `div_int` by 0 says `Duration.div_int: k is 0`. `abs()` of the most negative duration gives the longest one (see the proposals). A `DateTime` built by hand with fields out of range no longer overflows `to_unix`, `to_unix_ns` (now `OutOfRange`) or `diff` (saturates, as it does past 292 years).
- **std.deque** ([[lib/std/deque.my]]): `with_capacity` of a negative `n` or one past 2^30 is a runtime error naming it; `of` and a push past 2^30 elements are runtime errors (`deque: more than 1073741824 elements`). `d.iter()`, a `DequeIter<T>` that walks the ring.
- **std.set** ([[lib/std/set.my]]): `s.iter()` (a `ListIter` of the elements, as a map's `iter()`), and `impl Eq`: the same elements in any order.
- **std.heap** ([[lib/std/heap.my]]): `h.iter()`, a `HeapIter<T>` in `pop`'s order that pops its own copy. `sift_down` and `KeyedHeap.pop` compare the hole with half the length before `2 * hole + 1`, which overflowed past 2^30 elements.
- **std.btree** ([[lib/std/btree.my]]): `m.iter()` and `s.iter()`, `SortedMapIter<K, V>` and `SortedSetIter<T>` over a `Walk` of the linked leaves.
- **std.grid** ([[lib/std/grid.my]]): `new` of more than 2147483647 cells is a runtime error; `row` and `column` out of bounds are both runtime errors (`grid row 2 out of bounds for height 2`); `index` and `pos` out of bounds too; `neighbours4`/`neighbours8` compare without `x + 1` and give an out-of-bounds position's in-bounds neighbours.
- **std.graph** ([[lib/std/graph.my]]): a negative weight is a runtime error in `dijkstra`, `dijkstra_path`, `astar` and `dijkstra_dense` (`dijkstra: edge weight -3 is negative`); a path's cost past `int64`, or a cost plus `h` in `astar`, is a runtime error. `dijkstra_path` and `astar` share `search`, which names the function in its errors.
- **std.bitset** ([[lib/std/bitset.my]]): `fixed(n)` counts its words without `n + 63` (`words_for`), and a growable set's capacity is `bits_of(words)`, at most 2147483647, with `past(i)` deciding the one integer that saturation leaves out.
- **std.encoding**, **std.url** ([[lib/std/encoding.my]], [[lib/std/url.my]]'s error type only): `message()` and `Format` on `EncodingError` and `UrlError`.
- **std.list** ([[lib/std/list.my]]): the test function `sort_unstable_falls_back_to_heapsort`.
- Pages: Num, Time, Deque, Set, Heap, Btree, Grid, Graph, Bitset, Encoding, Url, and one row of [[Language/Standard-library/Iter]]'s sources. Set, Deque and Btree said `for x in s` "isn't possible yet" (the review gave those sentences to [[MYLA-427]]); they now describe `iter()`, as the change made them wrong.

## Evidence

- **Tests first.** Each item's cases were written before its code and failed:
  - num: 7 of 189 (`to_hex #7, #8`, `to_binary #8`, `format_fixed #15, #16`, `pow2 #5`, `f64_literal_bits #5`: "integer overflow" or a result where an error was expected).
  - time: 18 of 175 ("integer overflow" for each constructor, `+`, `-`, `mul_int`, `div_int`, `since`, `add`, `abs`, and the hand-built `to_unix`/`diff`), then 3 of 178 for `to_unix_ns`/`diff` with hand-built nanoseconds.
  - deque, set, heap, btree: the new cases didn't build (`unknown function 'slots_for'`, `type 'Deque<int32>' has no method 'iter'`, `operator '==' is not defined for 'Set<int32>'`).
  - grid: 10 of 28 (`new_cells #4` overflow, `row_of #2` gave `[]`, `column_of #2` read the next row's index, `index_of #2` gave 3, `pos_of #2, #3`, `neighbours_out_of_bounds`).
  - graph: `negative_cycle` didn't return (killed after 60 s); `cost_overflow` 0 of 4 ("integer overflow").
  - bitset: `words_for #5` and `bits_of #4` ("integer overflow").
  - list: the five heapsort mutants below.
- **The reproducers**, plain `build` (no `--checked`), before → after:
  - `bug_width.my`: hung (timeout 10 s, a 2 GB string) → `runtime error: to_hex: width -3 is negative`.
  - `durovf.my`: printed `-2562047h47m16.854775808s` for `abs()` of the minimum and wrapped sums (`-2ns`) → `abs()` is `2562047h47m16.854775807s`, then `runtime error: Duration.add: the sum is past a Duration's range (about 292 years)`.
  - `bug_capacity.my`: hung (timeout 10 s; interpreted "integer overflow") → `runtime error: deque.with_capacity: capacity 1073741825 is more than 1073741824`.
  - A growable `BitSet` holding 2147483647, `--checked`: "integer overflow" in `reserve` → inserts, contains, lists, removes it (1.1 s, 256 MB).
  - A `Heap<uint8>` of 2^30 + 2 bytes, `--checked`: "integer overflow" in `sift_down` → pops 0 then 100.
- **The heapsort fallback**: 100 elements from McIlroy's adversary run against a copy of `sort_unstable` in Python, stopped where the heapsort starts, the 72 elements not compared yet shuffled (seed 425), so the heapsort sorts a range that isn't a heap. Five mutants of the heapsort each pass the other 13 cases and fail this one: the left child always, the sift's test reversed, no swap of the top, no heapify, a heap one short. A mutant that drops the fallback (quicksort to the end) still sorts, only slower, and survives: catching it needs a comparison count, which an `Ord` without state can't keep.
- **Every runner**, `build/myla test lib/std/<m>.my --stdlib lib`, interpreted / `--native` / `--target aarch64-linux` (qemu) / `--target wasm32-wasi` (Node), all passed: num 189, time 178, deque 18, set 7, heap 8, btree 9, grid 28, bitset 76, graph 18, encoding 98, url 145, list 14. (`myla test` has no `--checked`: its native harness checks overflow already, D175.)
- **Speed**, natively, best of three on the shared machine, old library against new: `dijkstra_dense` over a 1000×1000 grid through `pos`/`neighbours4`/`index` 237–242 against 243–244 ms; `bfs_dense` through `neighbours8` 130–135 against 133–134 ms; a million `Heap<int>` pushes and pops 216–219 ms, `KeyedHeap` 256–266 ms, the same before and after. `SortedMap.iter()` over a million entries 7–9 ms against 12–16 ms for `items()`.
- **Suites**: bootstrap fixed point (byte-identical, 20210641 bytes; std.num is in the compiler); `tests.burn.test_doc_blocks` OK; `scripts/test.sh fast`: 829 tests, 1 failure, 3 skipped; `scripts/test.sh` (which runs `test_std_modules` interpreted and native, `test_compiler_parity`, `test_lsp`, `test_time`): 1478 tests, 1 failure, 336 skipped. The one failure, both times, is `test_embedded_std`, expected until the integrator's seed commit: `selfhost/embedded_std.my` is behind `lib/`.

## Proposals (decisions D184 leaves open)

1. **A negative width is a runtime error** in `to_hex`/`to_binary`, as D184 (2) lists widths; before, it meant no padding (a case pinned `to_hex(0, -3)` as `"0"`). Alternative: clamp a negative width to 0, which keeps that case.
2. **`Duration.abs()` of the most negative duration gives the longest positive one**, 1 ns shorter, as Go's `Duration.Abs` does; std.time follows Go's `Duration` in print form and `diff`'s saturation. Alternative: a runtime error, as for every other result past the range.
3. **`Heap.iter()` gives `pop`'s order, lazily** (a pop of its own copy per step, so `iter.take(k)` costs O(n + k log n)). Alternative: the heap's own order in O(1) a step, as Rust's `BinaryHeap::iter`, which is no order a program can use.
4. **`Set`'s `==` ignores the order**, and a `Set` isn't `Hash` (an order-free hash needs std.hash's `Hasher` inside a std module, which [[MYLA-360]] makes awkward). Alternative: `==` in insertion order, as the underlying map's order is visible.
5. **A grid's `neighbours4`/`neighbours8` of a position out of bounds give its in-bounds neighbours**, as their description says; `index`, `pos`, `row`, `column` out of bounds are failures, as `set`. Alternative: neighbours of an out-of-bounds position a failure too.
6. **`dijkstra_dense` refuses negative weights too**, though it returned (a node is settled once): its costs were wrong and could be its -1 for "not reached".
7. **`format_fixed` takes any non-negative `prec`**: a `prec` near `int32`'s maximum is a 2 GB string, as asked, without overflow. Alternative: a cap, as Python's "precision too big".
8. **The three error types' `Format` ignores its spec**, as `GridError`, `CsvError` and `JsonError` do (`TimeError` pads).

## Found on the way

- [[MYLA-480]]: std.list's sorts overflow on a list of more than 2^30 elements (`mid + width` in the merge passes, `2 * r + 1` in `sort_unstable`'s heapsort); `list.my` isn't this package's beyond its test.

## The owner's decision (2026-11-11)

The proposals stand as built (D189).

## Review 2026-11-12

Signed off in [[Project/Review-2026-11-12]], with a follow-up in [[MYLA-550]]: `bigint.from_int(5i64).shl(2147483646).bit_len()` overflows, and union-find and the dense graph forms give a raw index error for a bad argument (both outside this package's files).
