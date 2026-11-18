---
id: MYLA-781
title: "A sibling of a failed task sometimes runs past its next suspension point (t15 prints `never` on 16 workers under Wine)"
type: bug
status: todo
priority: medium
labels: [concurrency, runtime, round-7]
---
`tests/burn/concurrency_stress/t15_failure_beside_a_busy_sibling.my` checks D94 (2) and D97. A failure is reported when it happens, and the program ends once the busy sibling reaches its next suspension point, which is the `await log.note()` after its loop. The sibling must never get past that point, so `print("never")` must never run.

Under Wine on 16 workers it sometimes does run: stdout is `never` and stderr has the failure. This was seen in round 7's integration on 2026-11-18, at `fcfd651`: `scripts/windows-runner.py run --wine --runs 3` failed 1 of its 3 runs on 16 workers, with 152 of 170 cases passing. It was also seen in wave 6 (MYLA-744's and MYLA-727's runs, "t15 printed `never` once while the machine was loaded"). Natively, on aarch64 and on real Windows it has not been seen, so far.

A likely cause, to confirm first: the sibling's `await` of the actor call completes without suspending (the actor is free and the call runs at once). The await then never checks whether the group was cancelled, and the sibling goes on to its `print`. If so, an await that completes at once must still observe a cancellation that happened before it. Check both the interpreter and native code, and whether D97 says what an await that doesn't suspend owes.

- [ ] A reproduction that fails reliably: many runs, with a worker count and load that make it show, natively or under Wine
- [ ] The cause, and a fix that keeps D94 (2): no statement of a cancelled task runs after its next suspension point
- [ ] The case passes 100 of 100 times on 16 workers under Wine, and in the `windows` job
