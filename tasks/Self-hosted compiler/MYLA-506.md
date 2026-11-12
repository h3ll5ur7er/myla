---
id: MYLA-506
title: "Interpreter: `m[k] = v` and `m[k]` call a compound key's written `hash` twice, native code once"
type: bug
status: in-progress
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

- [x] `check_index` hands the place it found to the read or the update (or the place is found once per index and kept with the step), so each index finds its key once
- [x] A parity program with the reproduction

## What was built

**The interpreter finds each key once** ([[selfhost/interp.my]], [[Architecture/Interpreter]]):

- A read `m[k]` looks the key up once for the check and the value (`eval_index`).
- A place (`Place`: a variable and its steps) goes through `settle`, which checks each index as the read does and keeps where each compound map key was found, in its step (`Step.SIndex(key, node, place, hash)`, the map's own key in place of the program's). `update_cell` writes there without a lookup; an insert's place is found there, once. Assignments, `push`, `pop`, `append`, `append_char`, `append_byte`, `remove`, a `var self` call on a place and its write-back, and the containers `place_of` reads before the next index all go through it (`read_place`, `place_valid`, `readable` and `place_len` went: each looked the keys up again).
- A kept place stands while no variable changed since (`Interp.writes`, counted by `update_place` and at a change of task, against `Place.stamp`), or while the map still holds the kept key at that place (`still_at`: an argument may remove keys, and a removal compact the map, as `big[last].push(big.drop_below(17))` in the parity program does); else the key is looked up again.
- A number's or a string's key is looked up again where it is used: it runs no code of the program's, and a lookup costs less than keeping its place (keeping it in the step copies the place's list of steps).

**A compound assignment finds its place once, on both runners.** Natively `m[k] += 1` hashed twice: the read of `m[k]`, then the store's lookup. Both are needed only when the value can change the map between them (`m[k] += f()`). So when it can't, both runners now read and write the place with one lookup:

- `fused_compound` ([[selfhost/parser.my]], beside `compound_assign`, which shares the target node with the operator's left operand) says when: the target an element or a field at any depth whose indices are names or literals (as `hoisted` leaves them), the value something that calls nothing (literals, names, operators, casts, fields and elements of such: `m[k] += 1`, `xs[i][j] -= n * 2`, `cs[k].name += "d"`), at a scalar or a string.
- Natively `fused_assign` ([[selfhost/lower.my]]) takes the place's address once (made unique, a missing key trapping there as the read did), loads the old value, lowers the operator with that value as its left operand (`Lower.fused`, which `expr` hands back for the operand's node), drops the old value of a string and stores the new one.
- The interpreter's `exec_fused` does the same: the place settled as a read (its value kept by `settle`, `leaf_wanted`), the old value handed to `eval_binary` as the operand (`fused_val`), the result stored with the places kept.
- Errors are as before, on both runners: a missing key, a list index out of range, an overflow (checked and plain), a division by zero, an error in the value (11 cases by hand against the base, identical texts and positions).

**Decision (proposal).** That a compound assignment whose value calls nothing reads and writes its place with one lookup, so a written `hash` runs once for `m[k] += 1` (twice when the value has a call), on every runner ([[Language/Statements]] says so). Alternatives: two lookups always (native code's old behaviour; the interpreter made to look up twice too), or one always (the value evaluated with the place held, which a value that removes keys or changes the map would break).

## Evidence

- **Failing first**: the parity program `map_keys_hashed_once` ([[tests/burn/test_compiler_parity.py]]): a key type whose `hash` and `eq` print, through a set, a read, `+=` (by a name, by a computed key, with a call in the value), `contains` and `get_or`, a string's `+=`, an element of a list in a map (set, `push`, read, `+=`), a `var self` method, a struct's field in a map (set, `+=`), a map in a map, a tuple key, keys removed and compacted by the argument of a `push`, and `remove`. Its hash and eq calls per step, base interpreter / base native / now (both runners alike):

  | step | base interpreted | base native | now |
  | --- | --- | --- | --- |
  | `m[k] = v` | 2 | 1 | 1 |
  | `m[k]` | 2 | 1 | 1 |
  | `m[k] += 1` | 4 | 2 | 1 |
  | `m[k] += one()` | 4 | 2 | 2 |
  | `n[k][0] = 5` | 5 | 1 | 1 |
  | `n[k].push(3)` | 3 | 1 | 1 |
  | `n[k][1] += 4` | 7 | 2 | 1 |
  | `cs[k].n = 3` | 3 | 1 | 1 |
  | `mm[k][k] = 3`, `+= 3`, read (a map in a map) | 22 | 8 | 6 |

  Base: the interpreter's output differs from native code's (314 lines against 175); now both print the same 157, pinned.
- **Cost** (callgrind, instructions of `myla run`, the base interpreter (35b399e) against this one): an `[int: int]` written and read 20,000 times each 603.3 M → 598.8 M (−0.7%); `counts[w] += 1` on a `[str: int]`, 20,000 times, 460.1 M → 454.1 M (−1.3%); a `#derive(Eq, Hash)` struct key written and read 804.8 M → 765.2 M (−4.9%); a key with a written `hash` and `eq` set and `+=` 10,000 times each 7,040 M → 2,631 M (−62.6%); `adj[i % 100].push(i)` and nested reads 799.2 M → 789.6 M (−1.2%); a grid of lists, `g[a][b] += 1` and `g[a][b] = i` 966.6 M → 924.7 M (−4.3%). Native code of the same programs (callgrind of the binary): `counts[w] += 1` 5.12 M → 2.28 M, the written-hash one 8.96 M → 5.98 M, the grid 1.75 M → 1.55 M. A first version that kept every key's place, and looked the variable up for every plain assignment, cost up to +11% on the plain-key loops; an argument computed by a method call inside another call retained the whole interpreter around it (`self.deref(self.lookup_or_unit(…))`), so those are `let`s now.
- `#test` cases: `fused_assignment` (6), `is_member_place` (3), `changes_no_place` (2), `still_at` (3), `key_at` (2), `settle`, `settled_value`; `build/myla test selfhost/interp.my` 439/439, `selfhost/parser.my` 207/207, `selfhost/lower.my` 140/140.
