---
id: MYLA-547
title: "R5 The test harness: verdicts that still differ between runners"
type: bug
status: review
priority: medium
labels: [testing, harness, round-6]
---
Work package R5 of [[Project/Review-2026-11-12]]. Files: `selfhost/harness.my`, `lib/std/test.my`, the interpreter's runner. Follows [[MYLA-418]]. The first box builds the owner's decision 1, D191 (2026-11-12): a framed record the runtime writes in a test child.

- [x] **A multi-line panic is cut natively** (new with [[MYLA-418]], against D183): a message with a later line that starts `runtime error: ` is cut at that line on x86-64, aarch64 and wasm32, so `#test("a\nruntime error: b")[panic("a\nruntime error: b")]` passes interpreted and fails natively, `[panic("b")]` the reverse, and a failing test function shows only the tail (`repro-r5/harness/multiline_panic.my`). Stderr alone can't tell this from an `eprint` followed by a panic. Recommended: the runtime marks its own report in a test child (D189's proposal 1, taken up again), which also closes the forged marks below
- [x] **An empty `Err` passes** (old): a test function that returns `Err("")`, or an error whose `Format` gives `""`, is `PASS` on every runner, because `detail == ""` means "passed" in `lib/std/test.my` and in the interpreter's runner. Carry the verdict separately (`err_empty.my`)
- [x] **Exit statuses** (old): `#test(256)[exit(0)]` fails interpreted and passes natively, `[exit(256)]` the reverse, and `exit(-1)` is -1 interpreted and 255 natively. Mask to 0 to 255 in the interpreter's runner, or refuse an expected status outside it (`exit_range.my`)
- [x] `Err(())` is shown as `()` interpreted and `None` natively; an `Err` of a closure as `VClosure(, false)` and `<function>` (`err_unit.my`)
- [x] An interpreted case inherits `myla test`'s stdin and a native case gets an empty one: `echo x | myla test` fails interpreted and passes natively, and with an open stdin the interpreted run blocks (`stdin_case.my`). Decide whether a case gets a time limit
- [x] A case that writes the protocol's marks on stderr and then calls `exit(3)` passes natively; one that prints the case mark shifts the next verdicts on wasm32 (`proto.my`)
- [x] `myla test lib/std/rt.my --native` ends in `internal error: no function 'std$rt$alloc_tasks' to compile`; the exclusion is known and should be a message
- [x] `docs/Language/Attributes-and-testing.md`, line 200: "an index error or a missing map key can be expected interpreted only" is no longer true

## What was built

**D191, the record** (boxes 1 and 6). A test child's report is a record on stderr, `\u{1}myla-<nonce>\u{1}` then a kind, `:`, a number, `;` and, for the kinds with a text, that many bytes: `P:0;` passed, `F:<n>;<detail>` failed, `E:<n>;<message>` a runtime error, `X:<status>;` an exit, and `B:0;` on both streams before each case of a wasm32 run `--from <n>`. The nonce is the runner's (`now_ns()`, new for each `myla test`), passed as the harness's last argument (`--case <k> <nonce>`, `--from <k> <nonce>`), so nothing a case writes can pass for a record; the length frames the text, so a message of many lines is whole. `std.test`'s `reporting` copies the head into a cell of its own and puts it in the new runtime variable `__test_report`; std.rt's `test_record` writes the record and takes the head off (`__xchg64`), so a case's end has one record: `report_error` (every runtime error, out of memory and the stuck executor included) writes `E` instead of its report, `exit_program` writes `X` (the status the process ends with, `& 255`) or, after `__on_segv`'s stack overflow, `E:14;stack overflow` (the runner takes `__on_segv`'s own line off). A case that returned writes `P`/`F` in `std.test` (`case_end`, `child_done`), which takes the head off before `exit`. The runner (`record_in`, `case_outcome`) takes the last record of the run's head; without one the case ended outside the runtime: a signal, or a trap an emulator reported (`tools/wasm/run.mjs`'s `runtime error: …`), as before. wasm32's `__exit` now ends through `exit_program` like the other targets, so its exits have records too (and pass the exit hook).

The runtime change, for the runtime lane: `lib/std/rt.my`'s `exit_program`, `report_error`, `exec_stuck` (through `report_error` now, the same text) and the new `test_record`; the compiler's: `selfhost/codegen.my` (`__test_report`, 8 bytes in every target's runtime data) and `selfhost/runtime_wasm.my` (`__exit`).

**The verdict apart from the detail** (box 2): a case function of the harness gives `Option<str>` (None passed), the interpreter's `run_case` too; an `Err` fails whatever its text, and a FAIL with an empty detail is written `FAIL  e_str_empty` (`fail_line` in both).

**Exit statuses** (box 3): the interpreter's runner reports `exit(n)`'s status as the process ends with it, `n & 255`, as the record does natively; an expected `[exit(n)]` outside 0 to 255 fails without a call on every runner, `expected exit status 256: a status is 0 to 255`.

**`Err` shown alike** (box 4): `()` on both (the harness's repr of `()` was `None`, the interpreter's report says `()`), `<function>` and `<StringBuilder>` interpreted as natively.

**Stdin** (box 5): a case's stdin is empty on every runner. Interpreted, a running case's reads of descriptor 0 (`__read`, `__read_bytes`, `__poll`, and `__wait_readable`, `__wait_either` for the async reads) give end of input at once without an error.

**std.rt natively** (box 7): `myla test lib/std/rt.my --native` says `myla: lib/std/rt.my is std.rt, the runtime of every native program, whose own cases run interpreted only ('myla test lib/std/rt.my')` (in `selfhost/driver.my`'s `native_tests`, beside the platform module's message).

**The docs** (box 8): `docs/Language/Attributes-and-testing.md` (the record, exact matching of the runtime's own errors, an empty `Err`, statuses 0 to 255, the empty stdin, no time limit), `Standard-library/Test.md`, `Standard-library/Rt.md`, `Project/Known-issues.md`, the `myla` skill.

## Proposals (the owner decides)

1. **Exit statuses: masked, an expected one outside 0 to 255 refused** (built). `exit(n)` is reported as `n & 255` on every runner, the status the process ends with, and `[exit(256)]` or `[exit(-1)]` fails the case without a call on both runners. Alternatives: report `exit`'s argument as it was given on both runners (the record could carry it), so `[exit(256)]` passes although the process ends with 0; or refuse such an expected value at check time (a checker error), which needs the checker lane.
2. **A case's stdin is empty on every runner** (built). Alternatives: every case inherits `myla test`'s stdin (natively the children would share it, and a run would depend on its input), or a case gets lines named in the file (as a test program's `// input:`).
3. **No time limit for a case** (not built). A case that never ends stops the run, as before; with stdin empty the reported blocking is gone. Alternative: a per-case limit (a `--timeout <s>` of `myla test`, natively a kill of the child, interpreted a check in the loop), reported `FAIL  f: timed out after 60 s`.
4. **An empty `Err` is `FAIL  name`**, without a colon or detail (built). Alternative: a fixed text (`an Err with an empty text`), or the error's repr (`''`).
5. **`Err(())` is shown `()`** (built), as the interpreter's report shows the unit value elsewhere; the native repr of `()` changes from `None` (which a failing case returning `Option<()>` also showed).

## Evidence

Before (BASE `07445ab`, the reproducers of `repro-r5/harness/`): `multiline_panic.my` interpreted `1/3` with `boom #1` passing, natively `boom #1` FAIL (`got runtime error 'b'`), `boom #2` PASS, and `wraps_a_tools_error: runtime error: list index 3 out of bounds (len 3)\n  --> t.my:1:1` (the tail); `err_empty.my` `PASS  e_str_empty`, `PASS  e_format_empty` on both; `exit_range.my` interpreted `1/3`, natively `2/3`; `err_unit.my` `()` and `ERR: VClosure(, false)` against `None` and `<function>`.

After: every reproducer (`proto`, `multiline_panic`, `err_empty`, `err_unit`, `exit_range`, `stdin_case`, `expect`, with `x` on `myla test`'s stdin) gives the same stdout, stderr and status interpreted, `--native`, `--target aarch64-linux` (qemu) and `--target wasm32-wasi` (Node): `proto` 6/20, `multiline_panic` 1/3 (`boom #1` passes everywhere), `err_empty` 0/3, `err_unit` 0/2 (`()`, `<function>`), `exit_range` 2/3, `stdin_case` 1/1, `expect` 32/60. With an open stdin (`sleep 20 | myla test stdin_case.my`) the interpreted case passes at once.

Tests: `tests/burn/test_test_native.py` `_FRAMED` (the boxes in one file: the multi-line panic both ways, a test function's long message, the old marks and a `runtime error:` line before `exit(3)`/`exit(1)`, the case mark on both streams, the statuses, an empty `Err`, `Err(())`, an `Err` of a closure, a sync and an async read of stdin, a stack overflow) held to one report and one stderr on the four runners (`test_the_records_of_a_test_child`, `…_under_qemu`, `test_the_records_of_a_run`); `test_the_runtime_s_own_cases`; `lib/std/test.my`'s cases of `record_in`, `case_outcome`, `case_detail` (every kind, a record cut short, another run's record, the old marks), `cut_run`, `fail_line` (87/87 interpreted, `--native`, aarch64 and wasm32); the interpreter's `fail_line`.

Suites (at `cf963fa`, the bootstrap at its byte-identical fixed point): `scripts/test.sh fast` 877 tests, 2 failures, both the expected ones before the seed commit (`test_embedded_std`, and `test_project_commands`' `test_natively`, which passes with `MYLA_STDLIB=$PWD/lib`); `test_test_native` and `test_test_functions` 34 OK (the qemu and Node classes run); `test_compiler_parity`, `test_selfhost_cases`, `test_error_corpus`, `test_selfhost_checker`, `test_overflow` 680 OK; `test_std_modules` and `test_lsp` 169 OK; `scripts/test.sh` 1616 tests, 4 failures: the two above and two timing tests under a load of 5 on 4 cores (`test_round_trips_beside_many_waiting_frames` passes alone; `test_children_run_in_parallel`, the known one, fails alone too at that load and touches no test harness).

Found on the way: [[MYLA-588]] (x86-64 passes `exit`'s status to `exit_program` zero-extended; invisible today, the record masks it).
