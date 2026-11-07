# std.time

The clock (D124, [[MYLA-230]]): monotonic, so the difference of two readings is the time that passed; its zero is some fixed point in the past, not a date.

| Function | Result |
| --- | --- |
| `now_ns() -> int64` | The clock in nanoseconds |
| `now_ms() -> int64` | The clock in milliseconds |

The interpreter reads the same clock; with `MYLA_TIME=virtual` it reads one that moves only when no task is ready, to the next sleeper's deadline, so tests of timing logic take no time and order exactly.
