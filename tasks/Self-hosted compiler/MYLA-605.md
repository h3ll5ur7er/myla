---
id: MYLA-605
title: "Interpreter: a call of a builtin finds it by comparing its name with each builtin's"
type: improvement
status: review
priority: low
labels: [interpreter, performance]
---
Found by round 6's leftovers lane ([[MYLA-546]]). Once `read_line` no longer scans a byte at a time, the largest cost of reading lines interpreted is the dispatch of builtin calls by name: `eval_name_call` tests a builtin's name against one string after another (`nm == "std$task$cancel"`, `"__cancel_after"`, …, then `is_notify_primitive`, `is_raw_memory_primitive`, `is_wrapping_method`, `builtin_method_name`, …), each an `str_eq`. `names_a_builtin` already lets a program's own functions skip the chain (MYLA-380's follow-up), but every builtin call (`StringBuilder()`, `append`, `build`, `len`, `push`, `__read_bytes`, `__io_errno`) walks it.

Callgrind of `myla run` reading 6,000 lines (300 KB) with `read_line`, after [[MYLA-546]]: 1,047 M instructions, of which `std$rt$str_eq` 151 M (14 percent) and `equal_bytes` 44 M; by caller, `eval_name_call` 55 M, `is_raw_memory_primitive` 27 M, `names_a_builtin` 20 M, `lookup` 15 M, `is_wrapping_method` 12.5 M, `builtin_method_name` 11.8 M.

- [x] A builtin's call finds its case without comparing strings one by one: a code per name made once (a map from the name, or a code the checker records per call node), and the chains tested by that code
- [x] Measured: the 6,000 lines above, and the benchmark table of [[MYLA-546]] (plain loop, `fib(18)`, the map loop, generic code) before and after

## What was built

A code per builtin name, made once: `builtin_codes()` ([[selfhost/interp.my]]) maps each name `eval_name_call` took to a constant (`B_LEN`, `B_READ_BYTES`, …, in the order of its cases), a group of primitives another function takes (std.task's notifiers, the raw-memory primitives, std.net's lots and sockets, std.term's, the wrapping methods) to one code for the group (`G_NOTIFY`, …), and the interpreter keeps the map (`Interp.bcodes`). `eval_name_call` looks the name up once (`builtin_code`): no code, the program's or the library's function (what `names_a_builtin` decided with some 20 comparisons); else `eval_builtin_call` tests the code, case by case, an integer each. A method call (`xs.push(v)`, `h.wrapping_mul(k)`) looks its name up once too and hands the code on (`is_method_code` for `builtin_method_name`); the test of the receiver's type now comes before the formatted lookup of a written method of that name, which D151 rules out for a builtin's kind anyway. A primitive of the checker's lists that the table lacks is still found by those lists (`primitive_group`), only slower; `builtin_codes_agree`, a test function, checks the table against the checker's lists and `builtin_method_name`. Chosen over a code the checker records per call node: the checker is another lane's file, and one map lookup is already a few percent of what the comparisons cost.

## Evidence

Instructions (callgrind, `myla run` of the whole program, millions; the base is aef0b21's CLI, "600+604" the lane's first commit, "after" this one; MYLA-546's programs, and 6,000 lines of 1 to 99 bytes, 304,830 bytes, read by `read_line`):

| program | before (aef0b21) | 600+604 | after |
| --- | --- | --- | --- |
| start-up (`fun main() {}` with an empty loop) | 25.03 | 25.03 | 25.12 |
| plain loop, 20,000 iterations | 237.86 | 237.78 | 237.88 |
| arithmetic loop, 50,000 iterations | 888.81 | 888.36 | 888.46 |
| `fib(18)` | 104.32 | 104.32 | 101.90 |
| an `[int: int]` written and read 20,000 times | 607.33 | 607.09 | 607.19 |
| generic: `add<T>` 3,000 times, `sum`, `sorted`, `map`/`filter` | 739.55 | 739.37 | 703.84 |
| 6,000 lines by `read_line` | 755.62 | 729.62 | 658.34 |

- The lines: 729.6 M → 658.3 M by the codes (−9.8 %; with [[MYLA-600]]'s builder, read_line's, 755.6 → 658.3, −12.9 %), of which `std$rt$str_eq` 65.1 M → 13.6 M and `equal_bytes` 23.5 M → 18.0 M, against the map's lookups (`map_lookup` 34.7 M → 43.2 M, `str_hash` 10.6 M → 15.7 M). Wall time, the median of 7 runs, before → after: 139 ms → 114 ms. Generic code −4.8 %, `fib(18)` −2.3 % (its `print` and the builtins its library calls), the loops without a builtin's call unchanged, start-up +0.09 M (the table).
- **Tests.** `builtin_code`'s, `primitive_group`'s and `is_method_code`'s cases and `builtin_codes_agree` (`build/myla test selfhost/interp.my`: 453/453).
- **The interpreter's suites** (the lane's three tasks together, against aef0b21 in a copy of the repository; wall times on a machine shared with five lanes, CPU the robust measure), before → after: `tests.burn.test_selfhost_interp` 30.5 s → 28.0 s wall, 16.9 → 15.7 s CPU (10 tests before, 13 after: [[MYLA-600]]'s, [[MYLA-604]]'s and [[MYLA-620]]'s are new); `test_compiler_parity` 116.8 → 94.1 s wall, 90.0 → 82.6 s CPU; `test_selfhost_cases` 27.8 → 28.9 s CPU on the first run, again 27.2/27.1 → 27.2/26.5 s CPU (wall 12.3/14.0 → 16.9/18.7 s at a load of 7 on 4 cores; `myla test` of each of its files measured alone, 27.2 s → 26.8 s wall in all); `test_std_modules` 188.8 → 187.4 s wall, 169.6 → 162.5 s CPU. All pass.
- **The lane's tip** (MYLA-600, 604, 605, 620): `build/myla test selfhost/interp.my` 453/453, `selfhost/repl.my` 52/52; `scripts/test.sh fast` 895 tests, OK; `scripts/test.sh` 1,654 tests (342 skipped), one failure, `test_scheduling…test_a_wide_tree_of_tasks_needs_memory_for_its_depth` (native code's memory, lifo 236 MB against fifo 692 MB, the bound 3×): it passes alone, here and at aef0b21, so it was the load of the shared machine. `scripts/bootstrap.sh`: byte-identical fixed point (26,370,638 bytes); `selfhost/embedded_std.my` unchanged (no `lib/` change).
