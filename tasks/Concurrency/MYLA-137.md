---
id: MYLA-137
title: The native concurrency runtime
type: feature
status: done
priority: medium
labels: [concurrency, runtime, codegen, selfhost]
---
D89 (3, 4), after [[MYLA-138]] (D91): the self-hosted backend's runtime, without libc, made multi-threaded under the parity programs of [[MYLA-138]]; the Python backend keeps refusing concurrency (D91).

- [x] OS threads (`clone`), parking with `futex`, one worker per CPU (`sched_getaffinity`)
- [x] A heap per thread (arena and free lists), a cell freed on another thread than the one that made it
- [x] The executor: a run queue (work stealing later), actors' mailboxes and their running flag
- [x] Deep copies at crossings; `print` writing each line at once

## Where it starts

[[MYLA-138]] runs tasks on one thread: a ring of ready frames, `__exec_run`, tasks' first frames as their records. Everything one thread could share is shared: reference-counted cells cross tasks and actors (copy-on-write makes that invisible), the runtime's state is in globals (`__heap_ptr`, `__free_buckets`, `__exec_cur`, `__io_errno_val`, `__run_*_val`), a task's `task` word is read and written without atomics, `print` writes a value and its newline separately, and `exit` ends only the calling thread on Linux (`exit`, not `exit_group`).

## Design

1. **Who pays.** Only a program with tasks (frames mode, D91) gets the threaded runtime; any other program keeps today's, unchanged (D89 (6)).
2. **Thread state.** Each worker's runtime state (its heap, the frame it runs, the executor's stack pointer, `io` errno, `run`'s results) is in a block of its own, reached through `%fs` (`arch_prctl(ARCH_SET_FS)`), so a helper's access stays one instruction.
3. **A heap per thread** (D89 (4)). Each worker allocates from an arena of its own, at addresses that tell which (a fixed-size region per worker, so the cell header stays `[size][count]`). Freeing a cell of another worker's heap (a task moved between workers, a child's frame freed by its parent) pushes it onto that heap's remote list with an atomic exchange; the owner takes the list back when its free lists miss.
4. **Workers.** One per CPU (`sched_getaffinity`), or `MYLA_THREADS`; `clone` with stacks from `mmap`. A global run queue under a lock (work stealing later, measured); an idle worker parks on a `futex` and is woken by a push. The entry's task ending ends the process (`exit_group`), and so do `exit` and a panic in it.
5. **Waking.** A task's `task` word changes atomically: a parent waiting swaps itself in only over 0 (`lock cmpxchg`), a child ending swaps in its state (`xchg`) and queues the parent it finds.
6. **Actors** (D92): executors, as in Swift (below).
7. **Deep copies at crossings** (D89 (4)). An `async let`'s captures and result, `task.all`'s function values, an actor method's arguments and result: copied by generated per-type walks (`__deep_<T>`, as the clone helpers), so no count is shared between threads. Actor handles are the exception, shared by design: their cells' counts are atomic (`lock incq`/`lock decq`).
8. **Output.** `print` builds its line and writes it with one `write` (atomic for pipes up to `PIPE_BUF`).

### Decided (D92)

Option b, actor executors: a running flag and a queue of frames at the end of the actor's cell (after its fields, so their offsets and the drop helper stay as they are), behind a small lock word. Entering (`myla___actor_enter(actor, frame)`, tail-called with the resume point stored): the actor free, the frame goes on at once; busy, the frame joins the queue (linked through a fifth header word) and the worker returns to the executor. Leaving (`__actor_leave`): the next queued frame goes to the run queue holding the actor, or the actor is free. An awaited call of an actor's synchronous method enters, calls, copies the result, leaves; an async method of an actor enters at its start and after each `await`, and leaves before each `await` and at its end, its result copied first. Every suspension (waiting for a child, a turn after an awaited call, entering an actor) becomes such a tail call, so no frame is published before its function has left it. Deep copies are made by the sender (D92 (3)); `MYLA_THREADS` sets the number of workers.

Considered: *a lock per actor*, held between suspension points (a worker would wait briefly for a busy actor).

## Steps

1. [x] Thread state through `%fs`, `exit_group`, one `write` per `print` line (still one worker)
2. [x] Suspensions as tail calls into the runtime; atomic `task` words; actor executors (still one worker: the parity programs unchanged)
3. [x] Deep copies at crossings (`__deep_<T>`, a function value's environment through its drop function's neighbour), atomic actor counts
4. [x] Heaps per worker with remote frees
5. [x] Workers: `clone`, the shared queue, `futex` parking, `MYLA_THREADS`
6. [x] Stress programs (many tasks and actors across workers, under `MYLA_THREADS` 1 to 16), a speedup measured on a parallel workload, docs

## Evidence

- Step 1: in a program with tasks the runtime's per-thread variables (heap, free lists, the executor's current frame and stack, `io` errno, `run`'s results) are words of a block `%fs` points at (`tv`, `tls_offset`); other programs keep their symbols. Every exit is `exit_group`. `print` writes its line with one `writev` (`__print_line`; `strace` shows one `writev` per line), in every program: a million prints take 0.21 s instead of 0.30 s. The concurrency, held-failure, deep-task, corpus and parity tests pass; zero, the most negative `int` and `int64`, the largest `uint64`, an empty string and a two-byte `char` print as the interpreter prints them.
- Step 2: every suspension is a tail call into the runtime with the resume point stored first (`myla___yield`, `myla___wait`, `myla___actor_enter`, and the awaited call itself); the `task` word is swapped atomically (`lock cmpxchg` to park, `xchg` at the end and on failure). Actors have executors after their fields (`[lock][running][first][last]`, frames linked through a fifth header word, so `FRAME_RESULT` is 40): an awaited call of an actor's synchronous method takes the receiver and arguments into slots, leaves the caller's own actor, enters the receiver's, calls, leaves, yields and enters its own again; an actor's async method enters at its start and after every suspension and leaves before each and at its end; a failing task releases the actor it holds (`__actor_held`). On one worker an actor is never busy, so the order is unchanged: every concurrency, held-failure and deep-task test passes. 100,000 rounds of a synchronous and an async actor call with new strings as arguments print what the interpreter prints; a million, with an actor keeping nothing, peak at 11 MB.
- Step 3: a new IR instruction `deep T [%p]` (D85's rule for additions: the IR page, its text form, the verifier, the backend) replaces every heap value of the T at `%p` with a deep copy of its own and releases the originals; an actor handle stays shared, its count atomic (`lock incq`/`lock decq`). The backend's `__deepw_<T>` walks and `__deep_<cell>` routines reuse an unshared cell and clone a shared one first (with the copy-on-write clones), so copying what only the sender holds costs a walk. A function value's env is copied by the routine just before its drop function (`__deep_env`), composition's too. Copied: a child's captures by the parent (whose own reference to the child's env is released before the child is queued), an actor method's arguments as it starts and its result before it leaves. `values_cross_deeply` (lists, maps, strings, builders, a boxed and a list-recursive enum, tuples, closures with captures, actor handles, crossing into children and an actor and back) prints what the Python interpreter prints, at 11 MB over 300 or 3,000 rounds. `std.task` now hands each child only its half of the list: passing the whole list down copied it at every level (3,000 children peaked at 1.4 GB, now under 64 MB).
- Step 4: with tasks, `_start` reserves one region (`MAP_NORESERVE`) of a 4 GiB arena for each of up to 32 workers, so a cell's address tells its owner; a worker's heap starts at its arena (`__heap_init`). `__free` of another worker's cell pushes it onto that worker's list of cells freed elsewhere (`lock cmpxchg`), which the owner takes back whole (`xchg`) into its free lists when they miss. On one worker every test passes as before.
- Step 5: `_start` starts `MYLA_THREADS` workers (else one per CPU `sched_getaffinity` allows, at most 32): `clone`d threads with their state blocks (`CLONE_SETTLS`) and 8 MiB stacks. They share the ring of ready frames under a lock word; an idle worker spins 4,000 rounds, then sleeps on a `futex` a push wakes (only when one sleeps). The entry's task ending ends the process; every worker idle with nothing queued is a runtime error. With 4 workers on 4 CPUs every thread runs frames (`strace -f`: 3 `clone`s, `futex` and `writev` from each).
- Step 6: `test_tasks_on_any_number_of_workers` runs the 11 parity programs with child tasks, `values_cross_deeply` and the deep task trees 4 times each on 1, 2, 4, 8 and 16 workers: the same output and exit code every time; a longer run (30 times each, 1,950 runs) varied nowhere. `test_children_run_in_parallel`: eight CPU-bound children use 1.30 s of CPU in 0.34 s on 4 workers (1.28 s in 1.28 s on one). Measured: 8 × 60 million rounds take 5.09 s on one worker, 2.55 s on two, 1.30 s on four (3.93 times as fast). The held-failure tests run with `MYLA_THREADS=1`. Spinning before sleeping cut a program of tiny tasks from 5,847 `futex` calls to 57 (20 ms to 10 ms on 4 workers; 4 ms on one, 3 ms with the runtime of one thread). A program's start with 4 workers costs 0.15 ms more than with one.
- Compiling itself: 0.06% more instructions than after [[MYLA-138]] on the same input (2,605,331,412 → 2,606,791,413, the same assembly); on its own larger source 2,875,919,495, reaching its fixed point.
- Unit 621, integration 2, burn 796 (5 skipped) and the extension's 54 tests pass; the bootstrap reaches its byte-identical fixed point (5,944,191 bytes).
- Left for later: a work-stealing executor (measured against the shared queue), debug information for frame functions.
