---
id: MYLA-170
title: A failure isn't reported while a sibling runs without a suspension point
type: bug
status: todo
priority: medium
labels: [concurrency, runtime]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). `__task_fail` waits for every worker to stop (`__wait_stopped`, [[selfhost/codegen.my]]) before anything is printed. When a sibling of the failing task loops without an `await` that gives up its worker, the panic message appears only when the sibling finishes (3.6 s in the probe), and with an infinite loop all three implementations hang silently (the self-hosted interpreter and the Python interpreter wait for the sibling too). D94 (2) admits that such a task isn't stopped; [[Language/Concurrency]] says the failure "ends the program at once".

- [ ] Native: print the failure before waiting for the other workers, so a program whose sibling never suspends at least says what went wrong (the interpreters likewise)
- [ ] The page says that the report waits for the running tasks to reach a suspension point, and that a task looping without one keeps the program alive
- [ ] A stress program (`t15_failure_beside_a_busy_sibling.my`) with a sibling that ends after a bounded loop, checking the message arrives
