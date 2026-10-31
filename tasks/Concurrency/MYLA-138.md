---
id: MYLA-138
title: The stackless lowering of async functions
type: feature
status: done
priority: medium
labels: [concurrency, ir, codegen, selfhost, design]
---
D89 (5), first of the native steps (D91): `async` functions as state machines with heap frames in the self-hosted backend, on an executor with one thread; [[MYLA-137]] makes it multi-threaded after. The Python backend keeps refusing concurrency (D91).

- [x] A decision under D85: how the IR holds an async function's frame (slots as members of a heap object, or a new home for slots), its suspension points and resumption, and its calling convention
- [x] The self-hosted backend, with an executor of one thread (D91)
- [x] The concurrency parity programs natively, and deep task trees

## Design options (for the D85 decision)

Where it stands: D85 names "slots live in the stack frame" as an assumption a stackless lowering breaks. A slot is reached only through `addr $s`, `load`/`store` of a slot, `drop T $s`, `init`, `moved` and `bind`, so where a slot lives is the backend's business except at a suspension point, where the function returns to the executor with owned slots still live: the verifier would reject that `ret`.

**1. The frame: where an async function's slots live**

- a. *Every slot of an async function in its heap frame* (recommended): a slot gets a home, `stack` or `frame`; the backend turns `addr $s` into an offset from a frame register instead of `%rbp`. No liveness analysis, and the verifier is unchanged. Only async code pays, as D89 (6) wants.
- b. *Only the slots live across a suspension point*: smaller frames, but a liveness pass in the lowering, and a slot's home then depends on the function's suspension points.
- c. *No new home: the lowering rewrites frame slots to loads and stores at `%frame + off`*: no change to the IR's model, but the verifier no longer sees those values' ownership (drops at scope ends, moves), which the lowering would have to get right unchecked.

**2. Suspension and resumption**

- a. *A terminator `suspend L`* (recommended): the function stores its state, returns to the executor, and continues at `L` when resumed. For the verifier it is a `jmp L` (owned slots stay owned). The entry of an async function dispatches on the state to the resumption points, which the backend generates.
- b. *Ordinary code*: a `ret` with a status and a `br` chain at entry, plus a verifier exemption for async functions.

**3. Calling convention and waking**

- a. *Continuations, as Swift* (recommended): an async function is called with a fresh heap frame holding its arguments and a continuation (the caller's frame and resumption). When it finishes, it resumes its caller directly with `become` (D87, guaranteed tail calls), so finishing a deep chain costs one jump per level, once. A task is a chain of frames; the executor runs ready frames.
- b. *Polling, as Rust's futures*: an async function is a `poll(frame) -> ready | pending`; the caller polls its callee and suspends while it is pending. Simpler to lower, but every wake polls again from the task's root down to the frame that waited: O(depth) per wake.

**4. Frame allocation**

- a. *A heap cell per call, from the thread's heap* (recommended to start): sizes are known statically (the IR is monomorphic). A task allocator (Swift's: a stack of frames per task) can come later, measured.

## Decided (D90)

Options 1a, 2a, 3a and 4a: every slot of an async function in its heap frame, a `suspend L` terminator, continuations resumed with guaranteed tail calls, a heap cell per frame to start.

## Steps

1. [x] Programs of one task (no `async let`): async functions and lambdas compiled as ordinary ones (a valid schedule when there is no other task), `await` as its operand, async function types as function types; actors as handles to reference-counted cells (`Type.TActor` in the self-hosted checker), their fields reached through the handle; the compiler refuses an `async let` ("the compiler doesn't build 'async let' yet").
2. [x] The IR: slot homes, `suspend L`, the verifier, the text form; frame slots in `ir_x86`; the executor of one thread in the runtime
3. [x] Async functions lowered as `__new`/frame-function pairs; awaited calls of functions, methods and function values; continuations resumed with tail calls
4. [x] Tasks: `async let`, awaiting a child, scopes waiting for their children, turns after awaited calls, a failure in a child held for its `await`
5. [x] `std.task` and every concurrency parity program natively; deep task trees; docs

## Design of steps 2–4 (within D90)

- **Normalized first.** An async body is normalized as the self-hosted interpreter's is (`anf.my`): each `await` in a `let` of its own, so no temporary lives across a suspension; loop state, match copies and every other value that does live in slots.
- **The IR.** `IrFunc.frame`: the function's slots are in its heap frame (D90 1, all of them). `Term.Suspend(label)`: the function records `label` as where it resumes and leaves; when the instruction before it is a call, the call is made in place of the function (as `become`), otherwise it returns to the executor. The verifier treats it as a `jmp label`. The text form: `fun myla_f frame {`, `suspend L3`.
- **The frame.** A heap cell: `[resume fn][caller frame][state][task][result…][slots…]`. Parameters are slots in it holding owned copies (the caller may be gone when the callee runs): `myla_f__new(args)` allocates the frame, stores each argument (an aggregate's words, retained) and returns it; `myla_f__resume(frame)` is the IR function, its slots addressed from a register holding the frame (`%r15`, kept out of allocation there) instead of `%rbp`, none of them in a register, its entry dispatching on `state`.
- **Calls.** `await g(args)`: `fr = g__new(args)`, `fr.caller = frame`, then `suspend L` after `call g__resume(fr)` (through `__resume`, which jumps to `[fr]`, for a function value). At `L` the result is moved out of `fr`, which is freed. A `return` moves the value into the frame's result and ends with `__finish(frame)`: it resumes the caller with a tail call, or ends the task.
- **The executor (one thread).** A queue of ready frames; `_start` runs the entry's task and the loop. A frame that waits (a child not done, a scope's children) is parked with `suspend` and no call, and queued again when what it waits for ends. After an awaited call that didn't suspend (an actor's synchronous method), the frame goes to the back of the queue, so tasks take turns as in the interpreters.
- **Tasks and failures.** A task record holds its result, its state and the frames waiting for it. A panic or `exit` in a task other than the first records the failure and goes back to the executor's stack; `await` or the scope's end raises it in the parent, as the interpreters do.

As built, two refinements: the task record is the child's first frame (its `task` word: running, the frame waiting, done, failed by a panic or by `exit`), and every `async let x = e` is normalized to `async let x = (async || await e)()`, the self-hosted interpreter's child body (`task_body`), so the child gets copies of what `e` uses and both run tasks in the same order. An awaited `var self` method of a struct writes its frame's `self` back into the receiver; on a list element it is refused (the element could move while the method waits). The full description is in [[Architecture/Native-backend]].

## Evidence (step 1)

- `test_concurrency_programs_of_one_task_match_the_oracle` (`tests/burn/test_selfhost_codegen.py`): the 5 concurrency parity programs without `async let` and 4 actor programs (handles shared by copies, in a struct and a list; 200,000 actors made and released; reentrant calls; a recursive actor through `Option<Node>`) print what the Python interpreter prints. Releasing works: the 200,000-actor program peaks at 11 MB, at 24 MB when it keeps them all.
- The Python checker no longer calls a recursive actor an infinite struct (a handle is a reference).
- Compiling itself, the compiler runs 0.29% more instructions (2,587,410,658 → 2,594,793,999; one more `Type` variant to walk and one more kind of cell) with the same output.
- Unit 621, integration 2, burn 792 (5 skipped) and the extension's 54 tests pass; the bootstrap reaches its byte-identical fixed point (5,426,552 bytes).

## Evidence (steps 2–5)

- Before: `async_var_self_method` with `--async-frames` failed to compile ("an awaited call of an async 'var self' method"); the held-failure programs printed only `1` (panic) and `1 / inner goes on / 3` (exit) before dying, the child's failure ending the program at once.
- `test_concurrency_programs_match_the_interpreter`: the 16 concurrency parity programs and 5 actor and frame programs, natively, print and exit as the Python interpreter (those without `async let` also with `--async-frames`), each under 64 MB. `test_deep_task_trees_and_awaits`: 3,000 children through `task.all` calling an actor, and an async recursion 100,000 deep, in 11 MB. `test_child_failures_are_held_for_the_parent`: a panic, an `exit` from a grandchild, a trap in an unawaited child and children of synchronous calls, in the self-hosted interpreter's order. `examples/concurrency.my` joined the native corpus.
- 200,000 awaited `var self` calls on a field holding strings: 11 MB peak.
- Compiling itself: the compiler runs 0.16% more instructions on the same input (2,601,192,675 → 2,605,331,412 on the base commit's source, the same assembly); compiling its own larger source, 2,601,058,724 → 2,780,190,593 (the source grew by 1,030 lines), reaching its fixed point.
- Unit 621, integration 2, burn 794 (5 skipped) and the extension's 54 tests pass; the bootstrap reaches its byte-identical fixed point (5,733,179 bytes).
