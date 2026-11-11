# std.slice

What a slice takes (D142, D143): the index arithmetic the interpreter and the code generator share, so every runner takes the same elements.

```myla
import std.iter as iter
import std.slice as slice
from std.io import println

fun show(xs: [int]) -> str {
    var sb = StringBuilder()
    sb.append("[")
    for (i, x) in xs.iter() |> iter.enumerate() {
        if i > 0 {
            sb.append(", ")
        }
        sb.append(f"{x}")
    }
    sb.append("]")
    return sb.build()
}

fun main() {
    let xs = [10, 20, 30, 40, 50]
    println(f"{show(xs[1:^1])} {show(xs[::-2])}")
    // xs[::-2]: no start, no stop, a step of -2
    let r = slice.range_of(5, 0, false, false, 0, false, false, -2)
    println(f"{r.count} from {r.first}, {r.step} apart")
    // xs[1:^1]: the stop counts from the end
    println(show(slice.take(xs, 1, true, false, 1, true, true, 1)))
    // "héllo"[1:2] would end inside the two bytes of 'é'
    println(f"{slice.str_whole("héllo", 1, true, false, 2, true, false, 1)}")
}
// output:
// [20, 30, 40] [50, 30, 10]
// 3 from 4, -2 apart
// [20, 30, 40]
// false
```

| Function | Result |
| --- | --- |
| `range_of(n, start, has_start, start_end, stop, has_stop, stop_end, step) -> Range` | The indices a slice of something `n` long takes: `count` of them from `first`, `step` apart, the bounds clamped |
| `take<T>(xs: [T], …) -> [T]`, `take_str(s: str, …) -> str`, `str_whole(s: str, …) -> bool` | The elements taken, and whether a string's slice takes whole characters, no bound strictly inside a well-formed one (D174; what the interpreter and the compiler call) |
