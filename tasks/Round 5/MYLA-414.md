---
id: MYLA-414
title: "P1 The interpreter: generic code, receivers, errno"
type: bug
status: review
priority: high
labels: [interpreter, generics, overflow, round-5]
---
Work package P1 of [[Project/Review-2026-11-09]] (wave A1), with round 4's additions from [[Project/Review-2026-11-10]]. Files: `selfhost/interp.my`. Reopens [[MYLA-395]] and [[MYLA-391]]. Start by turning each reproducer into a failing test.

- [x] H1: arithmetic, comparison and formatting typed by a type parameter use the concrete type: bind type parameters in frames for every generic call, then trap (D175), wrap and compare as elsewhere; `float32` too (`[uint64].sorted()`, `xs.sum(0)`, generic `100i8 + 100i8`, `less(0u64, MAX)`)
- [x] Tests: `test_overflow` with a `T: Add` function, `xs.sum(0)` and `iter.sum`; a differential test of generic code per integer width, interpreted against native
- [x] H6 and M4: one "evaluate the receiver as a place" path instead of a case per receiver shape (`var self` on `xs[i]`, `m[k]`, a field of a call's result of type-parameter type)
- [x] An unresolved method is a runtime error with its position, never the printed value `ERR: VUnit` with exit 0
- [x] M5: reset the errno after a captured write (`myla test /absolute/path.my` with a printing case)
- [x] M8, the interpreter's half: a list or tuple `Err` of a test function prints its value, not `ERR: VList()`
- [x] L3: an actor's method calling the actor's own field that holds a function
- [x] L4: a `char` literal typed `uint8` (`let x: uint8 = 'a'`) prints as the number
- [x] S2: `__read_bytes` and `__write_bytes` without a boxed value per byte (interpreted `io.copy` of 32 MB: 2,096 ms, 27 ms before D177)
- [x] [[MYLA-380]]'s follow-up: interpreted `next` is 8 to 22 times a plain loop; measure and take what is cheap

## What was built

All in [[selfhost/interp.my]] (and one line of [[selfhost/repl.my]], which shows a `VBytes`); [[Architecture/Interpreter]] and [[Language/Generics]] describe it.

- **H1: every generic call binds its type parameters.** D172 bound them only in a program that calls a trait function on a type parameter (`type_env`, `%:T` per parameter, found by scanning every name in scope). Now each generic call does: the callee's frame gets one first variable, `%env`, an index into `Interp.envs` (the substitution), made once per call site and caller environment (`env_of`, memoized in `env_memo` by the call's id and the caller's `%env`), from the checker's `call_types` of the call, else by unifying the receiver's type with the impl's pattern (`impl_selfs`, now built for every program). A closure made in a generic function captures `%env` first. `typed_of(id)` (a type parameter's bound type: one tag test in the common case) is what an operator, a comparison's sign, a cast, float rounding and the wrapping methods read; `full_type_of(id)` substitutes a whole type for a format (`Option<T>`'s payload). Operators on a generic impl's type (`<` on `Rev<uint64>`, an `eq` written for a generic type) and `format` of one bind theirs by the operand's type. So `[2000000000, 2000000000].sum(0)`, `iter.sum`, generic `100i8 + 100i8` trap with `integer overflow` (at the operator, in `std/list.my` for `sum`), `[uint64].sorted()`, `less(0u64, MAX)`, `largest`, `is_sorted` compare unsigned, `div`/`rem` divide unsigned, a uint64 formats unsigned, and float32 rounds at each step, as natively.
- **H6, M4: one receiver path.** `eval_method_call` keys the method by the receiver's checked type, a type parameter's from its frame (`type_key`); with the binding above that is nearly always found. Without one (a written `eq` or `hash` the interpreter calls itself), the receiver is evaluated once, as a place when it is one (`place_rooted`: a variable, a field or an element of one), the method keyed by its value, and a `var self` method's final `self` written back to that place; `key_by_type` and MYLA-391's special case are gone.
- **Unresolved methods and functions** are the runtime error `internal error: no method 'm' found for a value of type 'T'` / `internal error: no function 'f' found` at the call (`call_error`'s cases), never a value printed as `ERR: VUnit`.
- **M5**: a captured write (`myla test`) sets `captured_io`, so `__io_errno` right after it reads 0, not what an earlier primitive left (the stale ENOENT that failed `println` in a file named by its absolute path).
- **M8, the interpreter's half**: a test function's `Err` of a list, tuple or map is shown in the report's form (`[1, 2]`, `(1, 'a')`, `['x': 1]`), a uint64 inside unsigned, through `typed_repr`.
- **L3**: a field holding a function is read through an actor's handle (`deref`), so `self.on(n)` in an actor's method calls it.
- **L4**: a char literal the checker typed as an integer (`let x: uint8 = 'a'`, `['a', 98u8]`) is the number.
- **S2**: `Value.VBytes(str)`, a `[uint8]` as the bytes of a host string, is what `__read_bytes`, `__str_to_bytes` and the `__run_*` results give; `__write_bytes` and `__bytes_to_str` take it as it is, and `len`, an index, a slice, `==` (against a `VList` too) and hashing work on it; any other use takes it apart into a `VList` (`list_values`, `byte_values`), so `push`, `pop` and an element's assignment turn it into an ordinary list.
- **MYLA-380's follow-up**: `func_idx`, `const_idx`, `is_enum_name`, `variant_enum` and `nullary_variant_enum` scanned every function, constant or declaration with string comparisons on each call, each `None` and each `Some(x)`; they read an index now (`func_ix`, `const_ix`, `enum_ix`, `variant_ix`, `nullary_ix`, the first declared of each name, as the scans found). A call by a name no builtin has (`names_a_builtin`) goes to the function without testing the 80 builtins' names first (`call_named`).

## Evidence

- **Failing first.** The reproducers (copied from the review's bundles): `bug_interp_generic_ints.my` printed `false`, `18446744073709551615`, `200`, `4294967296` interpreted (native `true 0 -56 0`); now `true`, `0`, then `integer overflow` at `a + b`. `bug_generic_u64.my`, `bug_generic_u64_ord.my`, `bug_generic_u64_format.my`, `bug_generic_f32.my`, `bug_generic_overflow.my`, `bug_list_sum.my` likewise agree with native code now (overflowing where native `--checked` does); `bug_list_sum_test.my` failed `myla test` ("got 4000000000"), passes. `bug6_…` printed `ERR: VUnit ERR: VUnit`, now `3 3`; `bug7_…` `3 10 20`, now `4 11 21`; `c3.my` `ERR: VUnit`, now `1200`; `char_u8.my` `a a a a`, now `97 97 97 97`; `h4_println_abs_path.my` "write failed: errno 2", now passes; `h3_err_of_test_function.my` `ERR: VList()`, now `[1]`.
- **The new tests, run against the base interpreter** (57fa3ef's `interp.my` in place, everything else the same): 23 failures in `test_overflow` (the 16 `test_generic_*` cases of `+ - * /` per width, `test_sums_in_generic_code_trap`'s `list_sum` and `iter_sum`, `test_myla_test_traps_in_generic_code`) and the parity programs `generic_code_per_width`, `receivers_of_type_parameter_type`, `actor_function_field`, `char_literal_typed_uint8`; with this change, all 47 pass. `test_byte_streams_hold_no_value_per_byte` against the first commit's interpreter: `read 15 ms, copy 1800 ms`, fails; passes now. `packed_byte_lists` (every list use on a packed `[uint8]`) passes on both, as it should.
- **Every std module's cases interpreted** (`myla test lib/std/<m>.my --stdlib lib`, 56 modules) pass after H1 and after S2: no library code relied on wrapping in generic code, so nothing moved to the `wrapping_*` methods.
- **callgrind** (instructions, `myla run`; base 57fa3ef, H1 the first commit alone, final both):

  | program | base | H1 | final |
  | --- | --- | --- | --- |
  | `fib(18)` | 402.3 M | 404.2 M (+0.5%) | 125.1 M (−68.9%) |
  | arithmetic loop, 50,000 iterations of `s = s + (i as int64) * 3 - 1; s = s ^ 5` | 924.3 M | 947.3 M (+2.5%) | 939.4 M (+1.6%) |
  | plain loop, 20,000 iterations with `%`, `==`, `<` | 339.7 M | 346.7 M (+2.1%) | 336.8 M (−0.9%) |
  | start-up (`fun main() {}`) | 41.34 M | 41.43 M (+0.2%) | 41.86 M (+1.2%) |
  | generic: `add<T>` 3,000 times, `sum`, `sorted`, `map`/`filter` | 1,395.7 M | 1,425.7 M (+2.2%) | 901.8 M (−35.4%) |
  | lazy `iter.range(0, 20000) \|> map \|> filter \|> sum` | 4,268.1 M | 4,264.8 M | 1,688.1 M (−60.4%) |

  H1's cost is the type test per operation (`typed_of`, kept a function's test: a `match` there retained and dropped the type, +6% on the arithmetic loop in the first version) and the binding per generic call (a memo lookup and one variable). Interpreted `next`: the lazy pipeline was 12.6 times the hand-written loop, 5.0 times now. What remains is evenly spread (allocation, copying values, name lookups by string); the next step would be method keys interned per call site.
- **S2**: interpreted `io.copy` of 32 MB of random bytes, file to file: 1,836 to 2,185 ms before, 31 ms now; `rw_now.my` (64 KiB reads and writes) 1,957 ms → 38 ms; the copies are byte-identical.
- **Suites**: `build/myla test selfhost/interp.my` 422/422 (new cases: `is_open`, `any_open`, `is_param_opt`, `opt_type`, `names_a_builtin`, `byte_values`, `is_vbytes`, `call_error`, `frame_env`, `typed_of`, `full_type_of`, `type_key`, `place_rooted`); `selfhost/repl.my` 47/47; `scripts/test.sh fast` 799 tests OK; `test_overflow` (43 tests, 18 of them new), `test_compiler_parity`, `test_selfhost_cases`, `test_error_corpus`, `test_selfhost_interp`, `test_selfhost_cli`, `test_test_functions`, `test_fs`, `test_process`, `test_stdio`, `test_stdin`, `test_net`, `test_term`, `test_examples_run`, `test_byte_copies`, `test_compress` pass; `scripts/test.sh` (all): 1,427 tests OK (336 skipped). `scripts/bootstrap.sh`: byte-identical fixed point (19,560,013 bytes); `selfhost/embedded_std.my` unchanged (no `lib/` change).

## Proposals (the owner decides)

- **The interpreter's own misses are runtime errors named `internal error: …`** (`no method 'm' found for a value of type 'T'`, `no function 'f' found`), at the call, exit 1. They mean the interpreter disagrees with the checker, never the program's fault, so the text says so. Alternatives: a panic of the toolchain with a stack (louder, but it loses the program's position), or the text of a user error (`no method …`), which would look like the program's.
- **Type parameters are bound at every generic call, eagerly**, rather than only where an operation typed by a type parameter needs them (the review's suggestion, measured above). The lazy alternative (look the type up from the call's arguments when an operator needs it) would cost nothing in non-generic code but needs the caller's types at the operator, which erasure no longer has.
- **`VBytes` stays a `[uint8]` only until a use that changes it**, which unpacks it into a `VList` for good (no repacking). Alternative: a packed list of every small integer type, which the interpreter's list operations would all have to know.

## The owner's decision (2026-11-11)

The proposals stand as built (D189).
