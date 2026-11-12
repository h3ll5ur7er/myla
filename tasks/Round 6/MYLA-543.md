---
id: MYLA-543
title: "R1 Native code: a value read from a container is freed by a later operand; order, leaks, recursive-enum keys"
type: bug
status: review
priority: high
labels: [lowering, native, memory, round-6]
---
Work package R1 of [[Project/Review-2026-11-12]]. Files: `selfhost/lower.my`, `selfhost/anf.my`, the drop and copy routines. Same lane as [[MYLA-415]] (reopened) and [[MYLA-542]]. All of it is older than round 5 and was found by the review's generators (`repro-r5/native/gen_rd.py`, `gen_h4.py`, `gen_loc.py`), which [[MYLA-555]] turns into burn tests.

- [x] **Use-after-free: a later operand frees what an earlier operand read** (high). [[MYLA-237]] protects call arguments; the same is missing for binary operands, index and slice bases, f-string holes and `format` arguments, map-literal keys, `match` scrutinees and the old value of `x op= f()` on a string element (25 of 90 forms tried). `repro-r5/native/uaf_binop_left.my`, `uaf_index_read.my`, `uaf_fstring.my`, `uaf_compound.my`:

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
- [x] **`c.g[c.k()].push(c.v())`** runs the index first interpreted (`push: 12`) and the value first natively (`push: 21`); the same for a map element. `insert`, `extend`, `sb.append` and a user's `var self` method agree. The review recommends the receiver's place first (decision 3); `repro-r5/native/order_index_push.my` Decided as recommended: D193 (the receiver's place first, then the arguments; native code changes).
- [x] **Leak** dropping an enum inside an enum that holds a recursive enum: RSS 61 MB against 13 MB (`leak_option_option_recursive_enum.my 100000`; `Option<Tree>` alone is fine)
- [x] **Leak** receiving `Option<[str]>` from a channel in a child task: 70 MB against 13.5 MB (`leak_channel_recv_option_list_in_child.my 200000`); `task.pool` with such jobs grew too
- [x] **A map keyed directly by a recursive enum** (`#derive(Eq, Hash) enum Lst { Nil, Cons(int, Lst) }`, `var m: [Lst: int] = [:]`) runs interpreted and is `internal error: main can't be lowered to the IR: a map keyed by a recursive enum` at build; wrapped in a struct, list, tuple or `Option` it works. Build it (decision 4), or refuse it in the checker with a real message ([[MYLA-313]]) Decided as recommended: D194 (built natively, as interpreted).
- [x] Float fields in a missing key's text: `Fl { f: 3.0, g: 10000000000.0 }` interpreted, `Fl { f: 3, g: 10000000000 }` natively; also `-0.0`, `1e+300`, `1e-07` ([[MYLA-441]])
- [x] wasm32: a list literal of 52,000 elements builds a module that Node refuses (`local count too large`)
- [x] H5's wording: a finite program (`id(x)` with a 65-deep literal type) is told its instances "nest without end … polymorphic recursion"
- [ ] … and `myla check` says `ok` for what `myla build` calls a type error: left open, a proposal below (the checker's file, [[MYLA-544]] lists it too)

## What changed

- **B2, the common cause.** Lowering reads a heap value out of a place borrowed (`expr`, `addr`: the string pointer in a list's element, a list's cell) and evaluates the next operand; when that operand calls a `var self` method on the same variable, the method replaces the container and releases what was read. [[MYLA-237]] had closed this for call arguments only (`later_writes`, `stage`). One rule now covers every operand that others follow: `Lower.operand` / `operand_addr` take the operand with a reference of its own (`stage`, released with the statement's temporaries) when `written_after(x, later)` says a later operand may write the variable `x` is read from; otherwise they borrow, as before. Used by: string `+`, `==`, `<`…, list and tuple `==`, a user type's operator and `eq`/`cmp` (`overloaded_scalar`, the aggregate `Binary`), so a compound assignment's old value (`h.xs[0] += h.s()` is `Assign(t, Binary(+, t, …))`); an index's base (`elem_read`: lists, strings, maps) and a slice's (`slice_expr`); an f-string's and `format`'s string holes (`format_call`; the other holes make new strings at once); a map literal's key (`held_operand`); the callee of a call through a function value, plain and async. `later_writes` is `written_after` of the rest.
- **C9, D193**: `push_elem` computes the holder's indices first (`held_place`) unless computing them after the value can't be told (`path_unaffected_by`: each index is literals, names, fields and operators the value can't write). `insert`, `extend`, `sb.append` and a user's `var self` method already did.
- **C10**: `CodeGen.owns_heap_seen` knew the generic types it had entered by name, so the inner `Option` of `Option<Option<Tree>>` looked like the outer one, "owning nothing", and the slot holding it wasn't an owner. It keys them by the whole type (`mono_token`). That was both leaks: a channel's `recv` gives `Option<Option<[str]>>`.
- **C11, D194**: a recursive-enum key is held in its slot as a box (as any member is, so the map's release, clone and deep copy already worked). `key_operand` gives a word pointing at the key's value, which `__khash_`, `__keq_`, `__mfind_` and `__krepr_` only read; `__mput_<K>` boxes a copy with references of its own when the key is new; `for k in m` reads the key out of its box.
- **Float fields in a key's text**: std.rt's `key_float_text` turns the print form into Python's `repr` (`3.0`, `-0.0`, `1e+300`, `1.5e-07`); `repr_scalar` calls it where the program has it (as with D183's texts, the tools' built-in library has it after the seed commit; `backend_std_functions` lists it).
- **wasm32**: `wasm_locals` gives a temporary that is written and read in one block only, each read after a write, a local it shares with the block's other temporaries that aren't live beside it (freed after its last reader, so no result shares its operands' local); the others keep one of their own. Node refuses more than 50,000 locals in a function.
- **H5's wording**: a refused instance asked for outside every generic instance (`cg.subst` empty) is a type the program writes, finite: `the instance of 'id' this call asks for is too large to build: its type arguments are 65 types deep (the limit is 64)`, without "polymorphic recursion". Inside an instance the old words stand.

## Evidence

- **B2**: the review's generator `gen_rd.py`, each of its 89 forms a program of its own, interpreted against native: **25 differ** with the compiler of 6e699ca (`bin_l` `s121!` for `s10!`, `bin_f` `out of memory`, `idx` an index error, `idx_g2` and `idx_ins2` nothing at all, `slice` empty, `fstr` `s121!`, `maplit`, `match_scrut` `bad`, `push_l` …), **0 after** on x86-64, `--checked`, aarch64 (qemu) and wasm32 (Node). The four `uaf_*.my` reproducers: the interpreter's output on the four. `gen_h4.py` (int, str, list: 1,905, 1,905 and 1,596 lines) and `gen_loc.py` (three element types in a plain function, an async function and a lambda) as whole programs: the same as the interpreter.
- Parity programs, one per family, each failing before (`s121!`, then `out of memory`; `list index 1 out of bounds (len 0)`; …) and passing after on the four runners: `operands_kept_when_a_later_operand_writes_their_variable` (string `+`, `==`, `<`, list and tuple `==`, a derived `eq`, a struct's `Add`, an `if` operand, `+=` on a list's and a map's string element), `bases_kept_when_their_index_writes_their_variable` (list, nested list both ways, map, a field of an element, a string's byte, slices of a list and a string, a function value from a list), `holes_and_keys_kept_when_a_later_one_writes_their_variable` (f-string, `format`, a map literal's key, a scrutinee's operand). More forms checked by hand the same way: an `if`'s and a `match`'s value as the left operand, a method's result, a tuple and a list literal, `ys.push(a + b)`, a hole with a spec.
- **C9**: parity program `a_method_call_takes_its_receivers_place_first` (`push: 21` and `map element push: 21` before, `12` after; the index read before a value that changes it; `index`/`value` printed in the interpreter's order for `g[at(1)].push(val(2))` and `bs[at(3)].append(…)`); `order_index_push.my`: all nine lines as interpreted, on three targets.
- **C10**: `test_nested_generic_enums_are_released` (peak memory of 20,000 and 200,000 rounds of `Option<Option<Tree>>`, `Wrap<Wrap<[str]>>`, `Result<Option<[str]>, …>`, a channel's `Option<[str]>` in a child and `task.pool` with such jobs): with the compiler of 6e699ca 14.2 MB and 142.4 MB, after 11.0 MB both. The review's two reproducers: 59.5 MB → 11.0 MB and 33.9 MB → 11.0 MB (100,000 rounds each).
- **C11**: parity program `recursive_enums_as_map_keys` (written, read, `+=`, `contains`, `remove`, `for k in m`, `keys()`, `get`, `get_or`, a copy changed while the original is, to a child task, a literal of a recursive enum holding strings, 2,000 writes over 50 keys): `main can't be lowered to the IR` before, the interpreter's output after on four runners; 20,000 rounds of building, copying and iterating such a map: 11.0 MB max RSS as at 1,000.
- **Key text**: `missing_key_with_float_fields` in `RUNTIME_ERRORS` (`Fl { a: 3.0, b: -0.0, c: 1e+300, d: 10000000000.0, e: 1.5e-07 }`, natively `3`, `-0`, `1e300`, `10000000000`, `1.5e-7` before), x86-64, aarch64 and wasm32; `key_float_text`'s 7 `#test` cases.
- **wasm32**: `test_a_list_literal_of_52000_elements` (Node: `local count too large` before; `52000`, `51999` after); the B2 generator and the parity programs above on wasm32.
- **H5**: `test_polymorphic_recursion_is_refused_where_it_is_built` gained the finite case (the new words, no "polymorphic recursion"); the three recursive cases keep theirs.
- **Cost**: the 13 benchmarks of `benchmarks/` built by the compiler of 6e699ca and by this branch: the same code, function by function (`objdump`, addresses aside; the only bytes that differ are data words, std.rt's line numbers), so B2's rule costs nothing on them: no benchmark has an operand followed by a `var self` call on its variable. Of the 37 examples, 4 differ, each by code that got shorter through [[MYLA-542]]'s narrower rule (`std.num.f64_literal_bits` 248 → 244 instructions, `str.split` 18 → 5, `str.splitn` 245 → 238).
- `scripts/bootstrap.sh`: byte-identical fixed point after each commit's build; `build/myla test` of `selfhost/lower.my` (147/147), `codegen.my` (361/361), `lib/std/rt.my --only key_float_text` (7/7).
- Suites (at d503468, the lane's last code commit): `scripts/test.sh fast` 867 tests, `scripts/test.sh` (full) 1,556 tests, 341 skipped; failures in both only `test_embedded_std` (expected until the seed commit) and, in the full run, `test_children_run_in_parallel`, which fails alone too and as much with the compiler of 6e699ca: under a load average of 6 to 7 on 4 cores, the eight children got about one CPU (cpu 1.14 s, wall 1.0 to 1.5 s, both compilers' binaries). `scripts/test-target.py aarch64-linux` and `wasm32-wasi` with `test_compiler_parity` and `test_native_runtime`: 2 of 2 suites pass on each.

## Decision this leaves open (proposal)

`myla check` accepts what `myla build` refuses for the instantiation limit (H5, D189's proposal 2). Recommended: keep it a property of native builds, as it is now, and say so (done in [[Language/Generics]]): the checker doesn't monomorphize, and polymorphic recursion, the case the limit is for, can't be seen without doing so. Alternatives: the checker applies the depth limit to the type arguments it infers at each call, which catches the finite case (`id` of a 65-deep literal) but not the recursive one; or `myla check` runs the lowering's instantiation walk, which costs check time ([[MYLA-552]]). Either belongs to the checker lane ([[MYLA-544]]).
