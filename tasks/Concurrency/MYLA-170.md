---
id: MYLA-170
title: A failure isn't reported while a sibling runs without a suspension point
type: bug
status: review
priority: medium
labels: [concurrency, runtime]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). `__task_fail` waits for every worker to stop (`__wait_stopped`, [[selfhost/codegen.my]]) before anything is printed. When a sibling of the failing task loops without an `await` that gives up its worker, the panic message appears only when the sibling finishes (3.6 s in the probe), and with an infinite loop all three implementations hang silently (the self-hosted interpreter and the Python interpreter wait for the sibling too). D94 (2) admits that such a task isn't stopped; [[Language/Concurrency]] says the failure "ends the program at once".

- [x] Native: print the failure before waiting for the other workers, so a program whose sibling never suspends at least says what went wrong (the interpreters likewise)
- [x] The page says that the report waits for the running tasks to reach a suspension point, and that a task looping without one keeps the program alive
- [x] A stress program (`t15_failure_beside_a_busy_sibling.my`) with a sibling that ends after a bounded loop, checking the message arrives

## Evidence

- Native: `__task_fail` claims the program and returns at once, the caller reports, then `__failed_wait` waits for the other workers before the exit. The Python CLI reports through `Interpreter.on_task_failure`, the self-hosted drivers through `Interp.on_failure`; the later report at the end is skipped (`reported`, `fail_reported`).
- A failing child beside a sibling that never suspends: natively on 4 workers the message is on stderr while the sibling still spins (it used to say nothing); the Python interpreter prints it and then waits for the sibling, as the page now says. On one worker such a sibling, once it runs, keeps the failing task from running at all (documented).
- `t15_failure_beside_a_busy_sibling` gives `('', 1)` everywhere (it prints nothing before its loop: whether the sibling has started when the failure comes depends on timing).
- Left for a decision: ending the program at once instead of waiting for the other tasks (a change to D97 (2)).
- Unit 622, integration 2, burn 826 (5 skipped) and the extension's 54 tests pass on commit 12f6e94; the bootstrap reaches its byte-identical fixed point (6,153,392 bytes).
