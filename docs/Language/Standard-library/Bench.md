# std.bench

Timing a closure over repeated runs ([[MYLA-403]]): a warm-up, then runs timed with [[Language/Standard-library/Time]]'s monotonic clock, and a `Report` with the minimum, the median and the spread, printed on one line. The module imports `std.time` and `std.list`.

```myla
import std.bench as bench
from std.bench import Report

fun fib(n: int) -> int {
    if n < 2 {
        return n
    }
    return fib(n - 1) + fib(n - 2)
}

fun main() {
    let r: Report = bench.run_n("fib 15", 10, () => fib(15))
    // fib 15  min 4.10 µs  median 4.32 µs  ±1.9%  (10 runs of 256 calls)
    let line = r.line()
    print(line[:11])
    print(r.runs)
    print(r.min <= r.median && r.median <= r.max)
    print(bench.duration_text(1234567.0))
    let words = ["b", "a", "c"]
    let s = bench.run_n("sort", 3, () => words.sorted())
    print(s.times.len())
}
// output:
// fib 15  min
// 10
// true
// 1.23 ms
// 3
```

| Function | Result |
| --- | --- |
| `run<T>(name: str, f: () -> T) -> Report` | `f` timed over runs for about a second: at least 5, at most 1000 |
| `run_n<T>(name: str, n: int, f: () -> T) -> Report` | `f` timed over `n` runs (at least one) |
| `run_for<T>(name: str, budget: time.Duration, f: () -> T) -> Report` | `f` timed over runs until `budget` has passed, at least one (`bench.run_for("parse", time.millis(200), f)`) |
| `black_box<T>(v: T) -> T` | `v`, through a call the compiler doesn't see through, so the work that made it isn't dead code |
| `summary(name: str, batch: int, totals: [int64]) -> Report` | The report of runs of `batch` calls that took `totals` nanoseconds each, for times measured some other way |
| `duration_text(ns: float64) -> str` | Nanoseconds with three significant digits and a unit: `12.3 ns`, `1.23 µs`, `123 ms`, `4.50 s` |

A closure that returns nothing is timed too: `T` is then `()` ([[MYLA-426]]; `()` is a type argument since [[MYLA-417]]), so `bench.run("step", () => step())` for a `fun step()` and `bench.run_n("sort", 10, () => { let ys = xs.sorted() })` work as a closure with a value does.

`struct Report { name: str, runs: int, batch: int, times: [float64], min: float64, median: float64, max: float64, spread: float64 }`: the times are nanoseconds a call of the closure, `times` each run's in the order of the runs (its time divided by the `batch` calls it made). `spread` is the median absolute deviation, the median of the runs' distances from the median: one slow run (a page fault, another process taking the CPU) moves neither it nor the median much, where it moves a mean and a standard deviation. `r.line()` is the report on one line, the spread as a percentage of the median, and `f"{r}"` the same (`Format`):

```text
fib 20  min 45.9 µs  median 50.8 µs  ±4.4%  (615 runs of 32 calls)
```

## How it works

- **The warm-up and the batch.** Reading the clock takes about 140 ns natively on x86-64 (`__clock_ns` is a system call, measured with `bench.run` itself), so a run of one call of a cheap closure would mostly time the clock. Before the timed runs, `f` is called in batches of 1, 2, 4, … calls until one batch takes a millisecond; that is the warm-up (caches, the allocator's free lists, the branch predictors), and the batch is how many calls each timed run makes. A run then reads the clock twice for a millisecond of work. The batch is at most 2^24 calls.
- **The runs.** `run` makes runs until a second has passed, at least 5 and at most 1000; so a closure that takes longer than 200 ms takes 5 runs and the warm-up's call. `run_n` makes exactly its runs and `run_for` runs until its budget is spent, both after the same warm-up.
- **Keeping the work.** Every result of `f` goes to `black_box`. Native code inlines only small functions of the caller's own module ([[Architecture/IR]], [[selfhost/inline.my]]) and calls a closure indirectly, so nothing the closure computes is dropped today; `black_box` is where a later optimiser has to stop. A closure that computes a value and drops it should give it to `black_box` itself: `() => { let x = work(); return bench.black_box(x) }`.
- **A clock that doesn't move.** Under `MYLA_TIME=virtual` the interpreter's clock moves only when tasks sleep. A batch of 1024 calls that took no time ends the warm-up with a batch of 1, every time is 0, and `run` stops at 1000 runs.
- **The interpreter** times the same way, but a call there costs about 10 µs, so its times say how long the interpreter takes, not how fast the code is: measure natively (`build/myla build`), with `--checked` off as a release build has it.

Measured natively on x86-64 with `bench.run` (2026-11-09):

| Closure | Median | Runs |
| --- | --- | --- |
| `() => 0` | 2.66 ns | 719 runs of 524288 calls |
| `() => time.now_ns()` | 146 ns | 810 runs of 8192 calls |
| `() => fib(10)` | 400 ns | 604 runs of 4096 calls |
| `() => fib(20)` | 50.8 µs | 615 runs of 32 calls |
| `() => xs.sorted()`, 1000 `int`s | 28.7 µs | `run_n`, 20 runs of 64 calls |
