---
id: MYLA-138
title: The stackless lowering of async functions
type: feature
status: todo
priority: medium
labels: [concurrency, ir, codegen, selfhost, design]
---
D89 (5), after [[MYLA-137]]: `async` functions as state machines with heap frames, in both native backends.

- [x] A decision under D85: how the IR holds an async function's frame (slots as members of a heap object, or a new home for slots), its suspension points and resumption, and its calling convention
- [ ] The self-hosted backend, then the Python backend
- [ ] Parity programs and deep task trees in both

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
