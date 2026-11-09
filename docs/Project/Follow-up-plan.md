# Follow-up plan after wave 4

The open follow-ups the standard library waves left ([[Project/Standard-library-roadmap]]), grouped by the compiler files they touch so that the batches run side by side with trivial merges, and shipped in two pull requests with one seed each (D156). Planned 2026-11-09; [[MYLA-385]] (`#derive(Json)`) and [[MYLA-376]] (the private helpers) run beside them.

| Batch | Tasks | Files | Pull request |
| --- | --- | --- | --- |
| 1 Test harness | [[MYLA-357]] (an empty-list receiver natively), [[MYLA-361]] (a large `uint64` in reports), [[MYLA-370]] (wasm32 stops at the first panic) | `selfhost/harness.my`, the test runners | toolchain fixes |
| 2 Checker | [[MYLA-382]] (`fill_in` rebuilds every body), [[MYLA-383]] (diagnostics), [[MYLA-388]] (`cancel` inside `std.task`), [[MYLA-394]] (D95 inside expressions), [[MYLA-316]] (a doc) | `selfhost/checker.my` | toolchain fixes |
| 3 Lowering and syntax | [[MYLA-392]] (an `await` in a nested `match`), [[MYLA-389]] (wasm32 release of deep values), [[MYLA-390]] (`for (k, v) in`, D174's slice bound, `append_char`) | `selfhost/lower.my`, `anf.my`, the drop routines, the parser | toolchain fixes |
| 4 Platform | [[MYLA-378]], [[MYLA-363]] (`stat`/`lstat`, a child's streams inherited or null, a descriptor as stdin, `close`'s errno), [[MYLA-369]] (`str` ↔ `[uint8]` in one copy, a builder's capacity) | `lib/std/platform*.my`, the primitive tables, `std.fs`, `std.process` | platform and gaps |
| 5 Language gaps | [[MYLA-379]] (`==` on `Option`/`Result`, `#derive` on generic types, D173's `IoError` text, `io.copy`'s buffer) | the checker's derive, after MYLA-385 | platform and gaps |

Left for later: [[MYLA-317]] and [[MYLA-368]] (research on the interpreter's and x86-64's speed), [[MYLA-377]] (`std.num` on `std.bigint`: an import cycle and check time), [[MYLA-311]] (a decision on integer overflow), [[MYLA-314]] (the roadmap's umbrella).
