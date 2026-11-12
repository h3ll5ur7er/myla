---
id: MYLA-605
title: "Interpreter: a call of a builtin finds it by comparing its name with each builtin's"
type: improvement
status: todo
priority: low
labels: [interpreter, performance]
---
Found by round 6's leftovers lane ([[MYLA-546]]). Once `read_line` no longer scans a byte at a time, the largest cost of reading lines interpreted is the dispatch of builtin calls by name: `eval_name_call` tests a builtin's name against one string after another (`nm == "std$task$cancel"`, `"__cancel_after"`, …, then `is_notify_primitive`, `is_raw_memory_primitive`, `is_wrapping_method`, `builtin_method_name`, …), each an `str_eq`. `names_a_builtin` already lets a program's own functions skip the chain (MYLA-380's follow-up), but every builtin call (`StringBuilder()`, `append`, `build`, `len`, `push`, `__read_bytes`, `__io_errno`) walks it.

Callgrind of `myla run` reading 6,000 lines (300 KB) with `read_line`, after [[MYLA-546]]: 1,047 M instructions, of which `std$rt$str_eq` 151 M (14 percent) and `equal_bytes` 44 M; by caller, `eval_name_call` 55 M, `is_raw_memory_primitive` 27 M, `names_a_builtin` 20 M, `lookup` 15 M, `is_wrapping_method` 12.5 M, `builtin_method_name` 11.8 M.

- [ ] A builtin's call finds its case without comparing strings one by one: a code per name made once (a map from the name, or a code the checker records per call node), and the chains tested by that code
- [ ] Measured: the 6,000 lines above, and the benchmark table of [[MYLA-546]] (plain loop, `fib(18)`, the map loop, generic code) before and after
