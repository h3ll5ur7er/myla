---
id: MYLA-576
title: "Native: every call of an actor's method from outside leaks 8 bytes"
type: bug
status: todo
priority: medium
labels: [runtime, lowering, concurrency, native, leak, round-6]
---
Found by [[MYLA-549]] while chasing the last item of its list (`manyserve3.my` of the review's bundle: a program that starts an HTTP server and a client 12,000 times grows 555 bytes a round on one worker). The leak isn't std.http's: a built program's resident memory grows 8 bytes for each call of an actor's method from outside, whatever the method returns, on one worker and on four. A plain `async fun` called the same way doesn't grow. std.http's server makes an actor call per worker when it stops (`Tally.worker_ended`, 64 by default) and, with a request limit, two per request, which is the 555 bytes a round (64 × 8, and the server's own few) and the client's 32 bytes a round of two requests.

```myla
import std.fs as fs
from std.io import println

fun rss() -> str {
    return match fs.read_to_string("/proc/self/status") {
        Ok(s) => {
            var out = "?"
            for l in s.lines() { if l.starts_with("VmRSS") { out = l } }
            out
        }
        Err(e) => "?"
    }
}

actor Box {
    n: int,
}

impl Box {
    fun get(self) -> int {
        return self.n
    }
}

#main
async fun main() {
    let b = Box { n: 1 }
    println(f"before: {rss()}")
    for i in 0..1000000 {
        let v = await b.get()
    }
    println(f"after 10^6 calls: {rss()}")
}
```

`build/myla build` and run with `MYLA_THREADS=1`: `before: VmRSS: 76 kB`, `after 10^6 calls: VmRSS: 7904 kB` (with four workers 4,600 kB); a method without a result (`fun bump(var self) { self.n += 1 }`) the same. The same loop over `await plain(i)`, an `async fun` that returns `i`: 72 kB, then 84 kB. Base `6e699ca`.

- [ ] Find what an actor call allocates and doesn't free (the call's frame or a record of `myla___actor_enter`'s queue, `lib/std/rt.my`, or the lowering of the call, `selfhost/lower.my`)
- [ ] A burn test: 10^6 actor calls in a bounded resident size, natively, on aarch64 and wasm32
- [ ] `manyserve3.my` (12,000 servers and clients) flat after the fix
