---
id: MYLA-480
title: "std.list: the sorts overflow on a list of more than 2^30 elements"
type: bug
status: review
priority: low
labels: [std, list, overflow]
---
Found in [[MYLA-425]]'s D184 sweep, in a file that package doesn't own. `sort`'s merge passes compute `mid + width` and `width *= 2`, and `sort_unstable`'s heapsort fallback `2 * r + 1`, before comparing them with the length, so a list of more than 2^30 elements overflows: a runtime error where overflow is checked, a wrong index in a plain build. [[lib/std/heap.my]] had the same `2 * hole + 1` and was fixed there by comparing the hole with half the length first.

Reproduction (natively; 2 min 37 s and about 2 GB):

```myla fragment
fun main() {
    var xs: [uint8] = []
    for i in 0..1073741826 {
        xs.push((i % 251) as uint8)
    }
    xs.sort()
    print(xs[0])
}
```

`build/myla build --checked` and run: `runtime error: integer overflow` at `var hi = mid + width` in `merged` ([[lib/std/list.my]]). The same holds for `merged_by` (`sort_by`, `sort_by_key`) and, with an input that reaches it, the heapsort of `sort_unstable`.

- [x] `merged`, `merged_by` and the run loop compare without forming a sum past the length (`width >= n - lo`, `width > n / 2` before doubling)
- [x] `sort_unstable`'s heapsort compares `r` with `end / 2` before `2 * r + 1`
- [x] Their cases still pass, interpreted and `--native`, and the timing of a million elements is unchanged

## Evidence

The index arithmetic is two helpers of [[lib/std/list.my]], each with `#test` cases at the edge of `int`: `run_end(lo, width, n)` (the end of a run, `lo + width` or `n`, compared as `width >= n - lo` before the sum) and `next_width(width, n)` (`width * 2` or `n`, compared as `width >= n - width`). The run loops of `sort` and `sort_by` and both merge passes (`merged`, `merged_by`) call them; `sort_by_key` sorts through `sort_by`. `sort_unstable`'s heapsort compares `r` with `end / 2`, computed once per sift, before `2 * r + 1`, as [[lib/std/heap.my]] does. It is written inline rather than as a third helper: a method of a built-in type (`impl<T: Ord> [T]`) doesn't inline its module's small functions ([[MYLA-526]]), and through a call the heapsort took 11.7 % more instructions (2,405 M against 2,153 M for a million `int`s).

- **Before.** The helpers written first with the old arithmetic (`lo + width`, then clamped; `width * 2`; `2 * r + 1`): `build/myla test lib/std/list.my --stdlib lib` gave `FAIL  run_end #3: runtime error: integer overflow`, `FAIL  next_width #5: …`, `FAIL  first_child #7: …`, `28/31 passed.`
- **After.** `24/24 passed.` (14 cases before, 10 new) interpreted, `--native`, `--native --target aarch64-linux` (qemu) and `--native --target wasm32-wasi` (`MYLA_EMULATOR="node tools/wasm/run.mjs"`). A heapsort helper's cases went with the helper.
- **2^30 + 2 bytes, once.** The task's reproduction (1,073,741,826 `uint8`s, then `xs.sort()`, then a check that each is at least the one before), `build/myla build --checked` and run natively: `1073741826 0 250 sorted true`, exit 0, in 2 min 27 s (on a machine shared with five other lanes). Before the change it stopped with `runtime error: integer overflow` at `var hi = mid + width` (the run this task was filed with; not repeated).
- **Speed.** A million `int`s natively (`benchmarks/quicksort`'s numbers), instructions by callgrind, old library against new:

  | Sort | Before | After | Change |
  | --- | ---: | ---: | ---: |
  | `sort` | 954.96 M | 956.85 M | +0.20 % |
  | `sort_unstable` | 492.53 M | 492.84 M | +0.06 % |
  | `sort_by((p, q) => p < q)` | 1,191.26 M | 1,192.70 M | +0.12 % |
  | `sort_by_key((p) => p)` | 1,565.42 M | 1,566.38 M | +0.06 % |
  | `sort_unstable`, all of it by the heapsort (a copy of the library with the depth limit 0) | 2,153.06 M | 2,155.95 M | +0.13 % |

  The same binary's count varies by about 0.2 M between runs. `sort`'s 1.9 M are the run loop's call of `run_end`, once for every 16 elements, which isn't inlined in a method (MYLA-526). Times (best of 9, shared machine, load 1 to 4): `sort` 132.9 and 131.7 ms, `sort_unstable` 124.6 and 119.7 ms, `sort_by` 170.2 and 174.1 ms, within the noise of the machine.
