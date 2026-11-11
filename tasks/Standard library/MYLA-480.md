---
id: MYLA-480
title: "std.list: the sorts overflow on a list of more than 2^30 elements"
type: bug
status: todo
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

- [ ] `merged`, `merged_by` and the run loop compare without forming a sum past the length (`width >= n - lo`, `width > n / 2` before doubling)
- [ ] `sort_unstable`'s heapsort compares `r` with `end / 2` before `2 * r + 1`
- [ ] Their cases still pass, interpreted and `--native`, and the timing of a million elements is unchanged
