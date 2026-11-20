---
id: MYLA-781
title: "A sibling of a failed task sometimes runs past its next suspension point (t15 prints `never` on 16 workers under Wine)"
type: bug
status: review
priority: medium
labels: [concurrency, runtime, round-7]
---
`tests/burn/concurrency_stress/t15_failure_beside_a_busy_sibling.my` checks D94 (2) and D97. A failure is reported when it happens, and the program ends once the busy sibling reaches its next suspension point, which is the `await log.note()` after its loop. The sibling must never get past that point, so `print("never")` must never run.

Under Wine on 16 workers it sometimes does run: stdout is `never` and stderr has the failure. This was seen in round 7's integration on 2026-11-18, at `fcfd651`: `scripts/windows-runner.py run --wine --runs 3` failed 1 of its 3 runs on 16 workers, with 152 of 170 cases passing. It was also seen in wave 6 (MYLA-744's and MYLA-727's runs, "t15 printed `never` once while the machine was loaded"). Natively, on aarch64 and on real Windows it has not been seen, so far.

A likely cause, to confirm first: the sibling's `await` of the actor call completes without suspending (the actor is free and the call runs at once). The await then never checks whether the group was cancelled, and the sibling goes on to its `print`. If so, an await that completes at once must still observe a cancellation that happened before it. Check both the interpreter and native code, and whether D97 says what an await that doesn't suspend owes.

- [x] A reproduction that fails reliably: many runs, with a worker count and load that make it show, natively or under Wine
- [x] The cause, and a fix that keeps D94 (2): no statement of a cancelled task runs after its next suspension point
- [ ] The case passes 100 of 100 times on 16 workers under Wine, and in the `windows` job (Wine: 800 of 800 below; the `windows` job runs once this is merged: only it can say)

## Evidence

**Also natively and under qemu.** CI's burn job on PR #83 (head `3add216`, run 44322691760, job 134866413943, 2026-11-18 14:44): `tests.burn.test_aarch64.Aarch64Tasks.test_stress_programs` failed for `t15_failure_beside_a_busy_sibling` with `('never\n', 1) != ('', 1)` at `MYLA_THREADS=16`. Here, at BASE `3add216` on 16 workers with the machine loaded (other lanes, Wine and qemu runs beside), t15 printed `never` in 13 of 4,000 native runs, 16 of 800 under qemu-aarch64 and 5 of 800 under Wine (another 258 of 600 under Wine with a copy whose failing task wrote a line to stderr before it panicked, at a load average near 100).

**The hypothesis refuted: no await missed a failure.** A copy of t15 read the failure flag (`__exec_failing`, through a function appended to a copy of std.rt) just before the sibling's `await log.note()` and again just after it, where `never` is printed. In every run that printed `never` (9 of 1,600 under Wine, 17 of 1,400 under qemu, 15 of 3,000 natively; 41 of 41), the flag was 0 before the await: the failure came after the sibling had passed its suspension point, and its turn's check (`exec_run`'s look at the flag before it resumes a frame, after the `__yield` that follows every actor call, `lower.my`'s `actor_call`) found nothing to stop for. In 5 of them (under qemu) it was 1 right after, a failure that came in the microseconds between that check and the print. An actor call that doesn't suspend does give a turn, and the turn does check (D94 (2): "the turn after an awaited call"); on aarch64 the check's exchange is followed by `dmb ish`. In the interpreter a failure ends the program at once, one task running at a time: nothing to change in either.

**The cause** is t15's timing: it assumed the failing task starts before the busy sibling's loop of about a millisecond ends. On 16 workers of a loaded machine (or qemu's) the failing task's worker may run later than that, and the sibling then prints `never` before the failure, legitimately.

**The fix**, in the test: the failure happens in the actor's method (`Log.fail` panics holding the actor), and the sibling prints `never` only when its call got the actor after it (`n > 1`): a call that came first has passed its suspension point before the failure; one that came after can't go on. Whichever comes first, nothing is printed, by construction; a runtime that resumed a frame after the failure would print it. (t15 also relied on a task that yields going behind the others, under MYLA_SCHED's orders; `test_scheduling` checks that promise.) Same load, same runs, after: 0 of 4,000 natively, 0 of 800 under qemu-aarch64, 0 of 800 under Wine, every one `('', <the failure>, 1)`. `tests.burn.test_concurrency_stress` passes.

**Suites** (2026-11-18, this branch): `scripts/test.sh` 1,859 tests OK; `scripts/test-target.py` x86_64-windows 39 of 39 suites, aarch64-linux 38 of 39 then 39 (test_children_run_in_parallel, [[MYLA-745]]), wasm32-wasi 39 of 39; `tests.burn.test_windows` and `test_windows_runner` 73 tests OK under Wine; `scripts/windows-runner.py run --wine --runs 3`: 153 passed, 0 failed, 17 skipped of 170 cases (round 7's integration: 152 of 170, t15 failing); the bootstrap's fixed point, `scripts/check-seed.sh` and its Windows run.

## Proposals

Accepted by the owner on 2026-11-19 as D299.

- Keeping t15's shape (a failure outside the actor) can't be made exact: nothing a program does happens after its failure, so a sibling that doesn't depend on the failing task always races it. A longer loop (10 or 100 times) would make it rarer, not gone, and past `STOP_WAIT_MS` the program ends without the sibling. Recommended: the failure in the actor's method, as built.
