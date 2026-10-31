---
id: MYLA-147
title: Cancellation of child tasks
type: feature
status: done
priority: medium
labels: [concurrency, language, runtime, interpreter, selfhost, design]
---
From the concurrency stress tests ([[MYLA-144]], test 8, "failure while sibling tasks are running"), the user's decision: add cancellation. A child failed while its sibling looped forever: both interpreters waited for the sibling at the scope's end and hung; native code ended the program at once, without waiting for the scope's other children (so a failing task's children could outlive their scope). With cancellation a failing scope stops its other children, then waits for them.

- [x] The design (a decision, D94): the user chose cancellation by failing scopes only; a cancelled task stops at its next suspension point where it gives up its worker; no syntax or library
- [x] The Python interpreter, the self-hosted interpreter, native code; test 8 ends with the failure everywhere, its children stopped

## Design (D94)

- **Python interpreter.** A task records its children (`kids`) and has a `cancelled` event; a scope unwinding by a failure (anything but `return`, `break`, `continue`, `become`) cancels its children, recursively, before joining them. Waiting for a child and an awaited actor call are suspension points: a cancelled task raises an internal `_Cancelled` there, which is never a failure of its own.
- **Self-hosted interpreter.** A task records its children and a `cancelled` flag; a scope closing by a failure cancels its children recursively, then waits as before. When the scheduler is about to run a cancelled task (which only happens after it suspended), the task starts leaving its calls as a failing one does, its scopes cancelling and waiting for their own children.
- **Native code.** Every frame knows its task (word 40) and every task its parent (word 56). A failing task sets its "children cancelled" flag (word 48) with `lock or`, then waits until no other worker's current frame belongs to a task below it; a worker publishes the frame it takes with `xchg` before it looks at the flags, so neither misses the other. A frame of a task below a failing one is dropped, not resumed, when a worker takes it from a queue; an actor handed to such a frame (recorded in word 64 by `__actor_leave`) is passed on. A cancelled task's frames are abandoned, as a failing task's already were: the program ends with the failure.

## Evidence

- Before: `t08_failure_cancels_a_looping_sibling` (a child panics while its sibling loops on an actor) timed out on both interpreters and natively ended with the failure at once, its sibling still running.
- After: `runtime error: failure`, exit 1, on both interpreters and natively on 1, 4 and 16 workers. `t08_failing_child_cancels_its_children` (a child task fails while its two children loop on an actor the rest of the program keeps using): `main still runs`, then the child's failure, everywhere, 90 more runs on 2, 8 and 16 workers alike (`tests/burn/test_concurrency_stress.py`).
- Unit 621, integration 2, burn 808 (5 skipped) and the extension's 54 tests pass; the bootstrap reaches its byte-identical fixed point (6,107,397 bytes).
