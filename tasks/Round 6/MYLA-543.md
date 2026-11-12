---
id: MYLA-543
title: "R1 Native code: a value read from a container is freed by a later operand; order, leaks, recursive-enum keys"
type: bug
status: todo
priority: high
labels: [lowering, native, memory, round-6]
---
Work package R1 of [[Project/Review-2026-11-12]]. Files: `selfhost/lower.my`, `selfhost/anf.my`, the drop and copy routines. Same lane as [[MYLA-415]] (reopened) and [[MYLA-542]]. All of it is older than round 5 and was found by the review's generators (`repro-r5/native/gen_rd.py`, `gen_h4.py`, `gen_loc.py`), which [[MYLA-555]] turns into burn tests.

- [ ] **Use-after-free: a later operand frees what an earlier operand read** (high). [[MYLA-237]] protects call arguments; the same is missing for binary operands, index and slice bases, f-string holes and `format` arguments, map-literal keys, `match` scrutinees and the old value of `x op= f()` on a string element (25 of 90 forms tried). `repro-r5/native/uaf_binop_left.my`, `uaf_index_read.my`, `uaf_fstring.my`, `uaf_compound.my`:

  ```myla
  struct H { xs: [str] }

  impl H {
      fun repl(var self) -> str {
          self.xs = [f"new{self.xs.len()}"]
          return "!"
      }
  }

  fun main() {
      var h = H { xs: [f"old{1}"] }
      print(h.xs[0] + h.repl())    // interpreted `old1!`, every native target `!`
  }
  ```

  `h.g[0][h.k()]` is `list index 1 out of bounds (len 0)` natively, and `h.m[1] += h.drop_one()` ends in `out of memory` (garbage bytes on wasm32).
- [ ] **`c.g[c.k()].push(c.v())`** runs the index first interpreted (`push: 12`) and the value first natively (`push: 21`); the same for a map element. `insert`, `extend`, `sb.append` and a user's `var self` method agree. The review recommends the receiver's place first (decision 3); `repro-r5/native/order_index_push.my` Decided as recommended: D193 (the receiver's place first, then the arguments; native code changes).
- [ ] **Leak** dropping an enum inside an enum that holds a recursive enum: RSS 61 MB against 13 MB (`leak_option_option_recursive_enum.my 100000`; `Option<Tree>` alone is fine)
- [ ] **Leak** receiving `Option<[str]>` from a channel in a child task: 70 MB against 13.5 MB (`leak_channel_recv_option_list_in_child.my 200000`); `task.pool` with such jobs grew too
- [ ] **A map keyed directly by a recursive enum** (`#derive(Eq, Hash) enum Lst { Nil, Cons(int, Lst) }`, `var m: [Lst: int] = [:]`) runs interpreted and is `internal error: main can't be lowered to the IR: a map keyed by a recursive enum` at build; wrapped in a struct, list, tuple or `Option` it works. Build it (decision 4), or refuse it in the checker with a real message ([[MYLA-313]]) Decided as recommended: D194 (built natively, as interpreted).
- [ ] Float fields in a missing key's text: `Fl { f: 3.0, g: 10000000000.0 }` interpreted, `Fl { f: 3, g: 10000000000 }` natively; also `-0.0`, `1e+300`, `1e-07` ([[MYLA-441]])
- [ ] wasm32: a list literal of 52,000 elements builds a module that Node refuses (`local count too large`)
- [ ] H5's wording: a finite program (`id(x)` with a 65-deep literal type) is told its instances "nest without end … polymorphic recursion", and `myla check` says `ok` for what `myla build` calls a type error
