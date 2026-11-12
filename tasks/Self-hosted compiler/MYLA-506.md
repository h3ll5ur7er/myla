---
id: MYLA-506
title: "Interpreter: `m[k] = v` and `m[k]` call a compound key's written `hash` twice, native code once"
type: bug
status: todo
priority: low
labels: [interpreter, maps, parity]
---
Found by [[MYLA-436]]'s lane. The interpreter finds a key's place more than once for one index: a read checks the key (`check_index`, which finds its place) and then reads it (`index_get` of `place_in`, which finds it again); a write checks the target (`check_index` with `assigning`) and then updates its cell (`update_cell`'s `key_place`); `m[k] += 1` does both. A compound key's place is its hash, so a key with a `hash` written for it is hashed two (read, write) or four (`+=`) times, where native code hashes it once (twice for `+=`, a read and a write). A `hash` with a side effect shows it:

```myla
#derive(Eq)
struct K {
    v: int,
}

impl Hash for K {
    fun hash(self, h: Hasher) -> Hasher {
        print("hash")
        return h.add(self.v)
    }
}

fun main() {
    var m = [K { v: 1 }: 1]
    m[K { v: 2 }] = 2        // interpreted: hash hash; native: hash
    print(m[K { v: 2 }])     // interpreted: hash hash; native: hash
    m[K { v: 2 }] += 1       // interpreted: 4 times; native: 2
}
```

It also costs the interpreter a second lookup of every map index, a plain key's too (a hash of its ints or strs).

- [ ] `check_index` hands the place it found to the read or the update (or the place is found once per index and kept with the step), so each index finds its key once
- [ ] A parity program with the reproduction
