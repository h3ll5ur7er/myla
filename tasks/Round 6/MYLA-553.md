---
id: MYLA-553
title: "R11 Small library gaps: `std.args`' spec checks, `iter()` on BitSet, Lru and Grid, the comments on import cost"
type: improvement
status: todo
priority: low
labels: [std, args, containers, round-6]
---
Work package R11 of [[Project/Review-2026-11-12]]. Files: `lib/std/args.my`, `bitset.my`, `cache.my`, `grid.my`, `list.my`, `encoding.my`, `fs.my`, `digest.my`. Follows [[MYLA-426]], [[MYLA-425]] and [[MYLA-428]].

- [ ] **`std.args` accepts specs that can't work** (`repro-r5/std/spec.my`): a `many` followed by a positional or a second `many`, a command named `""` or `-c` (unreachable), a name with a space, the short name `=`, a flag named `help` or short `h` that shadows the built-in one. The panic for a bad spec also points into `std/args.my:191`, not at the caller ([[MYLA-435]])
- [ ] **`iter()` on BitSet, Lru and Grid**: `for x in b.iter()` is "no method 'iter'" (`it2.my`); BitSet has `next_from` to build on. `for x in s` on a type with an `iter()` method could carry the help "write `s.iter()`", as pipelines do for lists
- [ ] The heapsort's tests don't kill `k = n / 2 - 1` (a heapify that skips the last parent): add an input with the last parent out of order ([[MYLA-480]])
- [ ] `args.same` (11 lines, 8 uses) and `encoding.same_bytes` are the `xs == ys` workaround [[MYLA-428]] removed elsewhere
- [ ] The comments that keep a helper private for its import's cost (`fs.my:736` "would add 2.5 ms to checking every program using std.io", `digest.my:315` "took 4 ms", and those in `net.my`, `archive.my`, `compress.my`, with the sentence in Conventions) were measured before lazy modules: std.fs calling `encoding.hex_encode` costs a std.io hello world 1.7 percent now. Share the helpers, or restate the reason with today's numbers
