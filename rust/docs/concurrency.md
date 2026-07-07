# Myla (Rust edition) — Concurrency

A bonus feature set inspired by Go's goroutines/channels and Swift's
async/await/actors. One unified runtime backs every surface form.

> **Implementation note.** The reference interpreter schedules tasks on OS
> threads (real parallelism) with `crossbeam` channels and `parking_lot` locks
> from `myla-runtime`. The surface syntax and semantics below are designed so a
> future M:N green-thread scheduler can be swapped in without changing programs.

## Keywords

`async`, `await`, `actor`, `spawn`, `go`, `chan`, `select`.

## Tasks: `spawn` / `go`

`spawn expr` (and the Go-flavored `go expr`) evaluates `expr` on a new task and
returns a **task handle**. The captured environment is moved by value.

```myla
let t = spawn fib(30)   // runs concurrently
let n = await t         // join and read the result
```

`spawn { ... }` runs a block for its effects:

```myla
spawn { ch.send(compute()) }
```

## Channels: `make_chan`, `send`, `recv`, `select`

Channels carry values between tasks. `chan<T>` is the type; `make_chan()`
constructs one.

```myla
let ch = make_chan()
spawn { ch.send(1) }
spawn { ch.send(2) }
let a = ch.recv()       // blocks until a value arrives
let b = ch.recv()
print(a + b)            // 3
```

Methods: `send(v)`, `recv() -> T` (blocking), `try_recv() -> Option<T>`.

`select` waits on multiple channels and runs the first ready arm:

```myla
select {
    x = jobs   => handle(x),
    y = quit   => return,
}
```

Each arm is `[binding =] channel => block`; the binding receives the value.

## async / await

An `async fun` runs as a task; calling it returns a handle that `await` joins.
`await` on a non-task value is the identity, so `await ch.recv()` is also valid.

```myla
async fun square(n: int) -> int { return n * n }

fun main() {
    let t = square(9)
    print(await t)      // 81
}
```

## Actors

An `actor` owns isolated mutable state. Its methods are **serialized** — only one
runs at a time — so shared state needs no manual locking. Construct an actor with
struct-literal syntax; mutating methods take `var self`.

```myla
actor Counter {
    count: int
    fun incr(var self) { self.count = self.count + 1 }
    fun value(self) -> int { return self.count }
}

fun main() {
    var c = Counter { count: 0 }
    c.incr(); c.incr(); c.incr()
    print(c.value())   // 3
}
```

## Sharing rules

Only `Clone + Send` values cross task/channel boundaries — which is every Myla
value, since aggregates are `Arc`-shared with copy-on-write. Tasks therefore
never observe each other's local mutations except through channels or actor
methods, keeping data-race freedom by construction.

See [`examples/concurrency.my`](../examples/concurrency.my) for a runnable tour.
