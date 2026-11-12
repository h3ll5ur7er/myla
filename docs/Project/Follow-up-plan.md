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

## Round 5 (2026-11-10)

The fixes of [[Project/Review-2026-11-09]] and [[Project/Review-2026-11-10]], as their work packages, after the owner's answers (D178 to D187). The packages are tasks in the epic `tasks/Round 5/`; the reopened tasks name theirs.

| Step | Packages | Pull request |
| --- | --- | --- |
| 0 | The board and the decisions (this section); [[MYLA-431]] P17, the seed size | two, no seed and the seed's own |
| A1 Toolchain | [[MYLA-414]] P1 interpreter, [[MYLA-415]] P2 lowering and native copies, [[MYLA-416]] P3a lexer and parser, [[MYLA-417]] P3b checker, [[MYLA-418]] P4 test harness | one, one seed |
| A2 Library | [[MYLA-419]] P5 runtime handles and processes, [[MYLA-420]] P6 text and streams, [[MYLA-421]] P7 regex, [[MYLA-422]] P8 HTTP and URL, [[MYLA-423]] P9 archives, [[MYLA-424]] P10 formats, [[MYLA-425]] P11 numbers and containers, [[MYLA-426]] P12 terminal and small modules, [[MYLA-427]] P13 docs and board; four or five lanes at a time | one, one seed |
| B | [[MYLA-428]] P14 helpers, [[MYLA-429]] P15 map compaction, [[MYLA-430]] P16 `--checked` with the overflow flag, [[MYLA-432]] P18 check time | one or two |

Why A1 comes first: the interpreter is the oracle, and it is wrong about generic integers (H1). Once it traps there, library cases that rely on wrapping will fail as they did after D175, and the library lanes should meet that at their start. A1 before A2 also orders the two cross-package dependencies: `lib/std/rt.my` (P2, then P5) and `std.bench` on unit closures (P3b's `()` as a type argument, then P12).

Each lane turns its reproducers into failing tests first. Before a wave is pushed, its reproducers from both reviews' bundles are re-run on the integrated tip, on every runner they name.

Left for later: [[MYLA-433]] (private fields and methods, a design), [[MYLA-434]] (async trait methods), [[MYLA-435]], [[MYLA-377]], [[MYLA-317]], [[MYLA-368]], and roadmap rows #10, #39 and #40. Part 2 of the review, the whole-codebase pass, is still to come.

## Round 6 (2026-11-12)

What [[Project/Review-2026-11-12]] left after round 5: six tasks reopened by narrow fixes, one bug raised to `high`, and thirteen packages, the tasks of the epic `tasks/Round 6/`. Round 5 itself is closed: its other 46 tasks are `done`.

The lanes are grouped by the files they touch, so they run side by side; a reopened task belongs to the lane of its file.

| Lane | Tasks | Files |
| --- | --- | --- |
| Lowering | [[MYLA-415]] (a closure that captures a recursive enum, copied to a task), [[MYLA-543]] R1 (a use-after-free across operands, an order, two leaks, recursive-enum keys), [[MYLA-542]] | `selfhost/lower.my`, `anf.my`, the drop and copy routines |
| Checker | [[MYLA-417]] (D178's call error on an actor's getter), [[MYLA-394]] (D95 in a shared head), [[MYLA-538]] (an unchecked impl bound, `high`), [[MYLA-544]] R2 | `selfhost/checker.my` |
| Lexer, parser, loader | [[MYLA-413]] (a program's own `std/` read lazily), [[MYLA-545]] R3 | `selfhost/lexer.my`, `parser.my`, `loader.my` |
| Interpreter | [[MYLA-414]] (a lost binding, the memo's growth, packed bytes in a report), [[MYLA-546]] R4 | `selfhost/interp.my` |
| Test harness | [[MYLA-547]] R5 | `selfhost/harness.my`, `lib/std/test.my` |
| Runtime | [[MYLA-548]] R6 | `lib/std/rt.my`, `net.my`, `term.my`, the platform modules |
| HTTP | [[MYLA-549]] R7 (a begun request holds a worker) | `lib/std/http.my` |
| Library | [[MYLA-460]] (the XML stream reader), [[MYLA-550]] R8 (D184's second pass), [[MYLA-553]] R11 | `lib/std/xml.my`; `yaml.my`, `io.my`, `bigint.my`, `archive.my`; `args.my`, the containers |
| Back ends | [[MYLA-551]] R9 (`--checked` traps out of line) | `selfhost/ir_x86.my`, `ir_a64.my` |
| Check time and seeds | [[MYLA-552]] R10 | the loader's cache, `scripts/` |
| Docs and board | [[MYLA-554]] R12 | `docs/`, `tasks/` |
| Generated tests | [[MYLA-555]] R13 | `tests/burn/`, the workflow |

Order: the lowering, checker, interpreter, HTTP and library lanes hold the high findings and come first. R13 only adds tests, so it can start at once, and its generators then guard the other lanes. R10 follows the parser lane, which shares the loader. Toolchain lanes end in one seed (D156).

Five decisions are the owner's before their boxes can be built (section 4 of the review): the test child's report ([[MYLA-547]]), raw mode and signals and a notifier closed beside a starting wait ([[MYLA-548]]), the order of `place[i()].push(v())` and a recursive enum as a map key ([[MYLA-543]]).

Left for later, as before: [[MYLA-433]] (the one to start next, as a proposal), [[MYLA-434]], [[MYLA-435]], [[MYLA-504]], [[MYLA-530]], [[MYLA-531]], [[MYLA-377]], [[MYLA-317]], [[MYLA-368]]. Part 2 of the review of 9 November, the whole-codebase pass, is still to come.
