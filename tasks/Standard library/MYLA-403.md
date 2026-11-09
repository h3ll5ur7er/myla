---
id: MYLA-403
title: "std.bench: time a closure over repeated runs"
type: feature
status: review
priority: low
labels: [stdlib, benchmarking]
---
Roadmap row #67 ([[Project/Standard-library-roadmap]]).

- [x] `bench.run(name, f)` (and a form with a count or a time budget): warm-up runs, then repeated runs of the closure, timed with `std.time`'s monotonic clock
- [x] A result with the runs, the minimum, the median and the spread, printed as one line (`name  min 1.23 ms  median 1.30 ms  (25 runs)`)
- [x] A way to keep the closure's result alive, so the work isn't optimised away (a `black_box`-like sink)
- [x] Cases interpreted and natively; a page below [[Language/Standard-library]] and the roadmap row

## Proposal (the owner decides)

Two choices the task leaves open:

1. **Runs are batches.** Reading the clock is a system call, about 140 ns natively, so a run of one call of a cheap closure times mostly the clock. The warm-up calls the closure in batches of 1, 2, 4, … until one takes a millisecond, and that batch is how many calls every timed run makes; the report gives times a call and says `(615 runs of 32 calls)`. Alternative: one call a run, which is exact only for closures of tens of microseconds and more.
2. **The spread is the median absolute deviation**, shown as a percentage of the median (`±4.4%`): one slow run moves neither it nor the median much. Alternatives: the standard deviation (moved by outliers), the interquartile range, or `max - min` (all fields of the report, so a program can compute them).

## Evidence

- **The API** ([[lib/std/bench.my]], [[Language/Standard-library/Bench]]): `run<T>(name, f: () -> T) -> Report` (runs for a second, 5 to 1000 runs), `run_n<T>(name, n, f)`, `run_for<T>(name, budget: time.Duration, f)`, `black_box<T>(v: T) -> T`, `summary(name, batch, totals: [int64]) -> Report`, `duration_text(ns: float64) -> str`; `struct Report { name, runs, batch, times: [float64], min, median, max, spread }` (nanoseconds a call), `r.line()` and `Format`: `fib 20  min 45.9 µs  median 50.8 µs  ±4.4%  (615 runs of 32 calls)`.
- **`black_box`** is a function of `std.bench`; native code inlines only small leaf functions of the caller's own module ([[selfhost/inline.my]]), and the closure is called indirectly, so nothing it computes is dropped today. The page says so and how a closure that drops a value should hand it over.
- **Cases:** `build/myla test lib/std/bench.my --stdlib lib`: `22/22 passed.` interpreted and `--native` (`summary` 3 cases, one with an outlier; `median_of` 2; `duration_text` 10, unit boundaries and rounding `999.7 → 1.00 µs`; `line` 3; test functions: `run_n` makes `n` runs with ordered statistics, `run_for` stops at its budget, a cheaper closure gets a bigger batch and a smaller median, `black_box` gives its value). The cases were checked against a broken module (no warm-up, a median that takes the upper middle): 19/22, the three that should fail failing.
- **Measured** natively on x86-64 with `bench.run` (the page's table): `() => 0` 2.66 ns (524288 calls a run), `time.now_ns()` 146 ns, `fib(10)` 400 ns, `fib(20)` 50.8 µs, sorting 1000 `int`s 28.7 µs; interpreted, `fib(20)` 258 ms (5 runs) and an empty closure 12.7 µs, which is what the page tells: measure natively.
- **Docs:** the page with a doc block that runs (interpreted and natively the same), its row on [[Language/Standard-library]], row #67 on the roadmap, the `myla` skill.
- **Suites** (the branch with all three tasks of the lane): `scripts/bootstrap.sh` reaches the byte-identical fixpoint; `scripts/test.sh fast`: 763 tests, the one failure `test_embedded_std` (`selfhost/embedded_std.my` behind `lib/` until the seed commit); `python3 -m unittest tests.burn.test_std_modules tests.burn.test_doc_blocks tests.burn.test_lsp tests.burn.test_toml tests.burn.test_compiler_parity tests.burn.test_selfhost_cases tests.burn.test_error_corpus tests.burn.test_selfhost_checker tests.burn.test_project_commands`: `Ran 733 tests in 491.9s OK (skipped=1)`.

## Comments

- 2026-11-09: the owner accepted the proposals: a fixed batch of calls per timed run, the spread as the median absolute deviation.
