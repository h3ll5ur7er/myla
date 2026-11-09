# Follow-up plan after wave 4

The open follow-ups the standard library waves left ([[Project/Standard-library-roadmap]]), grouped by the compiler files they touch so that the batches run side by side with trivial merges, and shipped in two pull requests with one seed each (D156). Planned 2026-11-09; [[MYLA-385]] (`#derive(Json)`) and [[MYLA-376]] (the private helpers) run beside them.

| Batch | Tasks | Files | Pull request |
| --- | --- | --- | --- |
| 1 Test harness | [[MYLA-357]] (an empty-list receiver natively), [[MYLA-361]] (a large `uint64` in reports), [[MYLA-370]] (wasm32 stops at the first panic) | `selfhost/harness.my`, the test runners | toolchain fixes |
| 2 Checker | [[MYLA-382]] (`fill_in` rebuilds every body), [[MYLA-383]] (diagnostics), [[MYLA-388]] (`cancel` inside `std.task`), [[MYLA-394]] (D95 inside expressions), [[MYLA-316]] (a doc) | `selfhost/checker.my` | toolchain fixes |
| 3 Lowering and syntax | [[MYLA-392]] (an `await` in a nested `match`), [[MYLA-389]] (wasm32 release of deep values), [[MYLA-390]] (`for (k, v) in`, D174's slice bound, `append_char`) | `selfhost/lower.my`, `anf.my`, the drop routines, the parser | toolchain fixes |
| 4 Platform | [[MYLA-378]], [[MYLA-363]] (`stat`/`lstat`, a child's streams inherited or null, a descriptor as stdin, `close`'s errno), [[MYLA-369]] (`str` ↔ `[uint8]` in one copy, a builder's capacity) | `lib/std/platform*.my`, the primitive tables, `std.fs`, `std.process` | platform and gaps |
| 5 Language gaps | [[MYLA-379]] (`==` on `Option`/`Result`, `#derive` on generic types, D173's `IoError` text, `io.copy`'s buffer) | the checker's derive, after MYLA-385 | platform and gaps |

Left for later: [[MYLA-317]] and [[MYLA-368]] (research on the interpreter's and x86-64's speed), [[MYLA-377]] (`std.num` on `std.bigint`: an import cycle and check time), [[MYLA-314]] (the roadmap's umbrella). [[MYLA-311]] is decided (D175: overflow traps where the program is checked, `int` stays `int32`); [[MYLA-395]] implements it in its own pull request after the toolchain fixes.

## Round 3 (2026-11-09)

After #53, #54 and #55, in one pull request with one seed:

| Lane | Tasks |
| --- | --- |
| Small modules | [[MYLA-402]] (the TOML writer), [[MYLA-403]] (`std.bench`), [[MYLA-404]] (`std.cache`) |
| Check time | [[MYLA-396]] (an imported module's `#test` cases unparsed), then [[MYLA-359]] (the implicit modules' check time) |
| Small fixes | [[MYLA-400]] (the last Option helpers), [[MYLA-332]]'s streaming CSV, [[MYLA-321]]'s page, [[MYLA-362]]'s wasm32 burn test |

Left for later: [[MYLA-397]], [[MYLA-398]], [[MYLA-401]] (language gaps), [[MYLA-399]] (the owner's decision), [[MYLA-377]], and roadmap rows #10, #39 and #40.

## Round 4 (2026-11-09)

After #56, in one pull request with one seed:

| Lane | Tasks |
| --- | --- |
| Loading | [[MYLA-359]]'s last box: an implicit module's function bodies parsed only once called, toward 5 ms for a hello world |
| Streams | [[MYLA-399]] (D177: `Read` and `Write` in bytes only), [[MYLA-405]] (`CsvError.message()`), [[MYLA-397]] (a platform module tested on its own target) |
| Language | [[MYLA-401]] (a list literal's element type from all its elements), [[MYLA-406]] (a field and a method of the same name), [[MYLA-398]] (a bound naming a module's trait) |
