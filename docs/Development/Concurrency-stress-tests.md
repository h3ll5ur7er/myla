# Concurrency System Stress Tests

> A language-neutral test plan for concurrency systems, kept as it was received (2026-10-31). [[MYLA-144]] turns it into Myla tests and records, for each example, what Myla guarantees ([[Language/Concurrency]], D89, D92).

This document provides language-neutral pseudocode for testing a programming language that aims to prevent concurrency problems automatically. Adapt the syntax to the language's concurrency, ownership, synchronization, and error-handling constructs.

A valid outcome may be compile-time rejection, safe serialization, isolated state, or a requirement for explicit synchronization. Accepting a program is only correct if its behavior matches the language's documented guarantees.

The examples use placeholder constructs: `spawn`, `await`, `parallel`, `channel`, `atomic`, `transaction`, and `cancel`. A `parallel` block starts its branches concurrently and waits for them to finish unless the example explicitly tests failure behavior.

## 1. Shared Mutation Through Hidden Aliases

A system may catch direct shared access but miss aliases hidden inside closures or containers.

```text
counter = Box(0)

callbacks = [
    () => counter.value += 1,
    () => counter.value += 1
]

parallel:
    repeat 100_000:
        callbacks[0]()
    repeat 100_000:
        callbacks[1]()

assert counter.value == 200_000
```

**Tests:** Alias tracking, closure captures, and implicit sharing.

**Expected:** Reject unsafe sharing or guarantee the exact count. Race-free individual reads and writes are insufficient if the increment itself is not atomic.

**Variants:** Pass aliases through generic functions, interfaces, nested containers, and recursive data structures.

## 2. Individually Safe Operations, Unsafe Transaction

Protecting individual accesses does not automatically preserve a multi-step invariant.

```text
account = Account(balance = 100)

function withdraw(amount):
    if account.balance >= amount:
        yield()
        account.balance -= amount
        return true
    return false

results = parallel:
    withdraw(80)
    withdraw(80)

assert count(results == true) == 1
assert account.balance == 20
```

**Tests:** Check-then-act races and the boundary of automatic atomicity.

**Expected:** If accepted with these guarantees, the check and withdrawal must behave as one protected operation. Otherwise, require an explicit transaction or equivalent construct.

## 3. Write Skew Across Separate Objects

Individual object protection may fail to preserve an invariant spanning several objects.

```text
alice.on_call = true
bob.on_call = true

parallel:
    transaction:
        if bob.on_call:
            alice.on_call = false

    transaction:
        if alice.on_call:
            bob.on_call = false

assert alice.on_call or bob.on_call
```

**Tests:** Transaction isolation and cross-object invariants.

**Expected:** Serializable transactions preserve the assertion. Weaker isolation may allow both people to go off call; that limitation should be explicit.

## 4. Deadlock Through Dynamic Resource Ordering

```text
function transfer(source, destination, amount):
    with exclusive(source):
        yield()
        with exclusive(destination):
            source.balance -= amount
            destination.balance += amount

parallel:
    transfer(account_a, account_b, 10)
    transfer(account_b, account_a, 20)

assert both_tasks_complete_within(deadline)
assert account_a.balance + account_b.balance == initial_total
```

**Tests:** Nested resource acquisition, dynamic aliases, and deadlock prevention.

**Expected:** If deadlock freedom is promised, prevent the cycle or reject the program. Otherwise, record this as outside the guarantee.

Also test identical resources:

```text
transfer(account_a, account_a, 10)
```

This variant can expose self-deadlock or inconsistent alias handling. The account's balance should remain unchanged after a successful self-transfer.

## 5. Deadlock Without Shared Memory

Ownership and race freedom alone do not prevent communication cycles.

```text
a = channel(capacity = 0)
b = channel(capacity = 0)

parallel:
    a.send("hello")
    b.receive()

    b.send("world")
    a.receive()
```

**Tests:** Protocol deadlock. With rendezvous channels, both branches try to send before either receives.

**Expected:** Reject the pattern, detect the deadlock, or document that protocol deadlock freedom is outside the guarantee. Detection is useful but is distinct from prevention.

Use an external watchdog so the test cannot hang the suite.

## 6. Reentrancy Across an Await

This is particularly relevant to actors that can process other messages while a method is suspended.

```text
actor Inventory:
    stock = 1

    async function buy(payment_service):
        if stock == 0:
            return SOLD_OUT

        await payment_service.charge()
        stock -= 1
        return SUCCESS

results = parallel:
    inventory.buy(payment_service)
    inventory.buy(payment_service)

assert inventory.stock >= 0
assert count(results == SUCCESS) <= 1
```

**Tests:** An invariant checked before suspension becoming invalid afterward.

**Expected:** Serialization across suspension, explicit reservation, or a diagnostic requiring reentrancy handling. Use successful mock payments to isolate this test from payment failure behavior.

## 7. Cancellation During Ownership Transfer

```text
pool = ResourcePool(size = 1)

task = spawn:
    resource = await pool.acquire()
    await cancellation_checkpoint()
    await use(resource)
    pool.release(resource)

cancel_at_selected_checkpoint(task)
await task.termination()

assert pool.available == 1
assert pool.resources_have_no_duplicates()
```

**Tests:** Cancellation safety, cleanup, and resource ownership.

**Expected:** No leak and no double release if automatic resource cleanup is promised. Otherwise, require a scoped resource or explicit cleanup construct.

Run a fresh instance for each cancellation location. Inject cancellation immediately before, during, and after acquisition, as well as during use and release. Include the boundary where acquisition succeeds but the awaiting caller has not resumed.

## 8. Failure While Sibling Tasks Are Running

```text
async function operation():
    local buffer = Buffer()

    parallel:
        repeat forever:
            await receive_and_append(buffer)

        await checkpoint()
        throw Failure()

try:
    await operation()
catch Failure:
    pass

assert no_child_tasks_of(operation).remain_running()
assert no_access_to_destroyed_locals_occurred()
```

**Tests:** Structured concurrency, exception propagation, and lifetime safety.

**Expected:** If structured lifetimes are promised, the failing scope must ensure its children terminate before destroying captured state. Ensure the receive operation supports cancellation; separately test the documented behavior of children that do not cooperate with cancellation.

## 9. A Stale Result That Is Race-Free

Safe memory access can still produce incorrect application behavior.

```text
async function search(query):
    result = await server.search(query)
    ui.results = result

first = spawn search("ca")       // deliberately slow response
second = spawn search("cats")    // deliberately fast response

await all(first, second)

assert ui.results.query == "cats"
```

**Tests:** Logical ordering across asynchronous work.

**Expected:** Unless the language explicitly models “latest request wins,” this requires application logic, such as request generations or cancellation with guarded publication. Use a deterministic mock server to force the older response to arrive last.

This is a boundary test for the language's claims, rather than evidence of a memory-safety defect.

## 10. Publication and Memory Visibility

If the language exposes relaxed memory or custom atomics, test its memory model directly.

```text
payload = 0
ready = false

parallel:
    payload = 42
    ready = true

    while not ready:
        yield()
    assert payload == 42
```

**Tests:** Whether observing a flag also makes preceding writes visible.

**Expected:** Reject unsynchronized access or provide synchronization semantics that justify the assertion. A scheduling yield should not be assumed to establish memory ordering unless explicitly documented.

If atomic flags are supported, compare release/acquire publication with relaxed operations. Evaluate each variant against its specified permitted outcomes; do not require stronger behavior than the memory model promises. Use a watchdog for nontermination.

## 11. Retryable Transactions With External Side Effects

```text
transaction:
    balance = account.balance
    await payment_gateway.charge(10)
    account.balance = balance - 10
```

Run two conflicting transactions and force one to retry. Use a mock gateway that records every charge.

**Tests:** Automatic retries duplicating effects that cannot be rolled back.

**Expected:** Forbid the effect, defer it through a defined mechanism, or require an explicit retry-safe protocol. An aborted or retried attempt must not silently create duplicate charges.

Deferring an effect alone does not solve every failure mode: test failure between transaction commit and effect delivery, and between successful delivery and acknowledgment. Any exactly-once claim needs a defined protocol for those boundaries.

## 12. Starvation Under Continuous Contention

```text
resource = SharedResource()
completed = atomic_array(worker_count, 0)

parallel for worker in workers:
    repeat 10_000:
        with exclusive(resource):
            completed[worker] += 1
        random_yield()

assert every(completed == 10_000)
```

**Tests:** Fairness and scheduler progress.

**Expected:** Finite workloads finish under the scheduler's documented progress assumptions. This finite test can catch regressions but cannot prove starvation freedom.

For a stronger variant, run a greedy worker that continuously reacquires the resource while other workers attempt a single acquisition. Check that each waiting worker makes progress under any promised fairness guarantee, then stop the greedy worker. Also vary worker priorities and processor counts.

## Running the Tests Effectively

### Define the guarantees first

For each example, record whether the language promises compile-time rejection, runtime safety, deadlock prevention, deadlock detection, fairness, or no guarantee. Keep compiler-rejection tests separate from executable tests.

### Explore controlled schedules

Use a controlled scheduler where possible. Introduce scheduling points around shared accesses, suspension, resource acquisition and release, cancellation, and message delivery. Explore bounded schedules systematically and supplement them with randomized runs.

Record the seed and scheduling decisions so failures are reproducible. A failing trace should include task identities, relevant state changes, synchronization events, and cancellation or exception delivery.

Controlled scheduling alone may not expose weak-memory behavior. Use memory-model litmus testing or appropriate native-runtime stress tests for those guarantees.

### Check three dimensions separately

| Dimension | Question | Example failure |
| --- | --- | --- |
| Safety | Did anything invalid happen? | Lost update, negative stock, stale access |
| Progress | Can the work finish? | Deadlock, starvation, livelock |
| Cleanup | Did failure leave resources or tasks behind? | Leaked resource, orphan task, duplicate release |

### Vary the execution conditions

- Run with one worker and multiple workers, including more tasks than workers.
- Vary channel capacities, contention levels, task creation order, and resource identity.
- Inject exceptions and cancellation at supported boundaries.
- Exercise debug and optimized builds, and supported processor architectures.
- Test interactions between features after the individual cases work: transactions with cancellation, actors with callbacks, and ownership transfer with sibling failure.

### Interpret results carefully

Passing stress tests increases confidence but does not prove a universal concurrency guarantee. A timeout is evidence of missing progress in that run; inspect the trace to distinguish deadlock, starvation, scheduler delay, and an inadequate deadline. Claims of prevention should be supported by the language's static rules, runtime protocol, or formal model as well as tests.
