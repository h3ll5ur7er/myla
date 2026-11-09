# std.slice

What a slice takes (D142, D143): the index arithmetic the interpreter and the code generator share, so every runner takes the same elements.

| Function | Result |
| --- | --- |
| `range_of(n, start, has_start, start_end, stop, has_stop, stop_end, step) -> Range` | The indices a slice of something `n` long takes: `count` of them from `first`, `step` apart, the bounds clamped |
| `take<T>(xs: [T], …) -> [T]`, `take_str(s: str, …) -> str`, `str_whole(s: str, …) -> bool` | The elements taken, and whether a string's slice takes whole characters, no bound strictly inside a well-formed one (D174; what the interpreter and the compiler call) |
