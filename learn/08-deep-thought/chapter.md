title: Deep Thought
emoji: 🧠
tagline: Tests, concurrency and JSON. Seven and a half million years in the making.

The last chapter, for the second greatest computer in all of space and time.

- `#test(args)[expected]` above a function is a test case; `myla test` runs them all. Writing them is your job too.
- `async fun` may wait: `await f()` waits for its result. A program that awaits starts at `#main async fun main()`.
- `async let x = f()` starts `f` as a child task, running in parallel until you `await x`.
- An `actor` is a struct whose methods run one at a time: calling one is `await a.m()`.
- `#derive(Json)` makes a struct readable and writable as JSON with `std.json`.

See [[Language/Attributes-and-testing]], [[Language/Concurrency]] and [[Language/Standard-library/Json]]. The answer is coming. You may not like it.
