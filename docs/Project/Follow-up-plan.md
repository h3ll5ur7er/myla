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

The owner took the five recommendations of the review's section 4 (2026-11-12): D191, the test child's report as a framed record ([[MYLA-547]]); D192, raw mode restored on SIGINT, SIGTERM and SIGHUP, and D195, a wait on a closed notifier returning at once ([[MYLA-548]]); D193, the receiver's place before the arguments, and D194, a recursive enum as a map key natively ([[MYLA-543]]).

The waves, each one pull request with one seed:

| Wave | Lanes |
| --- | --- |
| 1 | Lowering ([[MYLA-415]], [[MYLA-543]], [[MYLA-542]]), checker ([[MYLA-417]], [[MYLA-394]], [[MYLA-538]], [[MYLA-544]]), interpreter ([[MYLA-414]], [[MYLA-546]]), library A ([[MYLA-460]], [[MYLA-550]]), HTTP ([[MYLA-549]]), generated tests ([[MYLA-555]]) |
| 2 | Lexer, parser and loader ([[MYLA-413]], [[MYLA-545]]), test harness ([[MYLA-547]]), runtime ([[MYLA-548]]), back ends ([[MYLA-551]]), library B ([[MYLA-553]]), and the leftovers of wave 1 (the rest of [[MYLA-546]], [[MYLA-564]], [[MYLA-565]]) |
| 3 | Check time and seeds ([[MYLA-552]], after the loader), docs and board ([[MYLA-554]], last, as it touches every task) |

**Built (2026-11-13).** All three waves are built and every package and reopened task is in `review`, waiting for the owner's sign-off. Wave 1 is pull request #65, merged; waves 2 and 3 are each one pull request still to be opened, wave 2's with its seed commit (`dafd287`, D156), wave 3's to end with one.

The round filed these tasks. Five were fixed in it and wait in `review` with their lanes' packages; the others are candidates for the next round, by area:

| Area | Fixed in the round (`review`) | Candidates for the next round |
| --- | --- | --- |
| Checker and loader | [[MYLA-564]]: an impl type parameter that only a bound names is said so, not told to apply to an impossible type | [[MYLA-584]]: a program's own `std/` directory gets the library's privileges in the checker (raw memory, `__` primitives), as it goes by the `std$` prefix of a name, not by the loader's root (`medium`); [[MYLA-609]]: an integer literal past `int32` in an `if` or `match` arm doesn't take another arm's `int64` |
| Interpreter | [[MYLA-565]]: an invalid spec of `x.format(spec)` on a builtin `T: Format` is reported at the call on every runner | [[MYLA-600]]: a `StringBuilder` holds each byte in a word (a 20 MB string takes 280 MB to build); [[MYLA-604]]: every turn of the scheduler polls every task that waits for a descriptor; [[MYLA-605]]: a builtin's call is found by comparing its name with each builtin's (14 percent of reading lines) |
| Native runtime and back ends | [[MYLA-572]]: a read of `n` bytes no longer allocates `n` before it reads (4 MiB at most); [[MYLA-576]]: an actor's method called from outside no longer leaks 8 bytes a call | [[MYLA-588]]: x86-64 passes `exit`'s status zero-extended; [[MYLA-592]]: a SIGSEGV sent by `kill` is swallowed once; [[MYLA-608]]: a third of a hello world's check is page faults, and huge pages for the heap's chunks take a millisecond off it (`medium`, a decision) |
| Standard library | [[MYLA-580]]: `math.ldexp` clamps the exponent first (`ldexp(1.5, 2147483647)` took 18 s interpreted, 2026-11-12, `b71e0e5`) | [[MYLA-610]]: two comments in `std.task` and `std.time` weigh an import by its check cost before the lazy modules |

The next design is [[MYLA-433]], private fields and methods, as the review suggests: until it, the library's own steps are public and its pages list them as such (`args.check_name`, `bitset.past`, `http.finish`, …, [[MYLA-554]]).

Left for later, as before: [[MYLA-433]] (the one to start next, as a proposal), [[MYLA-434]], [[MYLA-435]], [[MYLA-504]], [[MYLA-530]], [[MYLA-531]], [[MYLA-377]], [[MYLA-317]], [[MYLA-368]]. Part 2 of the review of 9 November, the whole-codebase pass, is still to come.

## Windows (2026-11-14)

The owner's plan for the Windows target ([[MYLA-165]]), decisions D209 to D216. Its tasks are numbered from MYLA-700, apart from the ids other work takes meanwhile.

| Wave | Tasks | Files |
|---|---|---|
| 1 | [[MYLA-700]] the target record (the part of [[MYLA-262]] the port needs); [[MYLA-701]] the platform interface in Myla's terms (D209) | the driver and the backends' target switches; `lib/std/platform*.my`, std.rt, std.fs, std.process, std.io, std.net, the interpreter's primitives |
| 2 | [[MYLA-702]] hello world as a static `.exe`, Wine in CI (D210 to D212, D215) | `selfhost/ir_x86.my`, `runtime_x86.my`, a `platform_windows.my`, the harness |
| 3 | [[MYLA-703]] memory, threads, thread-local state, stack overflow; [[MYLA-704]] files and paths; [[MYLA-705]] processes | `platform_windows.my`, std.rt's runtime, std.path |
| 4 | [[MYLA-706]] IOCP and Winsock; [[MYLA-707]] the terminal and signals; [[MYLA-708]] the Windows runner | `platform_windows.my`, std.rt's reactor, CI |
| 5 | [[MYLA-709]] bootstrapping on Windows (D214, D238 to D241); the hang of wave 4's socket case ([[MYLA-753]], [[MYLA-754]], [[MYLA-756]], D242, D243) | the scripts, a third seed, CI; the poller, std.rt's lock, std.http's keeper |
| 6 | The host's own modules, scratch directories and console lines ([[MYLA-723]], [[MYLA-729]], [[MYLA-734]]); signals and the poller's glances ([[MYLA-744]], [[MYLA-755]]); the platform interface's leftovers ([[MYLA-716]]); debug information on Windows ([[MYLA-757]]); portable process cases and the language server's builtin calls ([[MYLA-727]], [[MYLA-710]]) | the loader and the driver; `platform_windows.my`, the runtime, std.rt; the platform modules, std.io, std.process, std.http; `selfhost/dwarf.my`, the target record; std.process's cases, the language server |

Each wave is one pull request. Wave 1 changes `lib/std/platform_wasm.my`'s interface with the others; a web application developed alongside may touch the same file, so the waves merge master often.

## Round 7 (2026-11-17)

What [[Project/Review-2026-11-17]] left of round 6, the features of 13 November, the website and the Windows waves: of the 78 tasks that waited in `review`, 64 are `done` and 14 are reopened, [[MYLA-715]] is raised to `high`, and eleven packages are the tasks of the epic `tasks/Round 7/`. Master's CI was red at the reviewed commit (`e153ee08`): [[MYLA-705]]'s case on the Windows runner, which comes first in its lane.

The lanes are grouped by the files they touch, so they run side by side; a reopened task belongs to the lane of its file.

| Lane | Package | Reopened tasks in it | Files |
| --- | --- | --- | --- |
| Checker | [[MYLA-790]] R7-1 | [[MYLA-612]] (an operator impl's bounds unchecked), [[MYLA-584]] (`exit` and `cancel` by name) | `selfhost/checker.my` |
| Lowering and ANF | [[MYLA-791]] R7-2 | [[MYLA-543]] (`m.contains(k())`), [[MYLA-551]] (far trap branches on aarch64) | `selfhost/lower.my`, `anf.my`, `ir_a64.my` |
| Interpreter and harness | [[MYLA-792]] R7-3 | [[MYLA-435]] (a generic `#track_caller` function), [[MYLA-547]] (the record in one write); [[MYLA-715]] | `selfhost/interp.my`, `harness.my`, `lib/std/test.my` |
| Parser and loader | [[MYLA-793]] R7-4 | | `selfhost/parser.my`, `loader.my` |
| HTTP | [[MYLA-794]] R7-5 | [[MYLA-549]] (eviction closes the newcomer), [[MYLA-755]] (glances by turns or time) | `lib/std/http.my`, `rt.my` |
| Router and JSON | [[MYLA-795]] R7-6 | [[MYLA-613]] (`static_files` on Windows, patterns) | the router in `lib/std/http.my`, `json.my` |
| Numerics | [[MYLA-796]] R7-7 | [[MYLA-587]] (matrix shapes, `inverse`, cases), [[MYLA-585]] (`sinh`, `tanh`, the implicit module's cost) | `lib/std/matrix*.my`, `float.my`, `math.my`, `fmt.my` |
| XML | [[MYLA-797]] R7-8 | [[MYLA-460]] (a cut character, the DOCTYPE scan) | `lib/std/xml.my` |
| Windows | [[MYLA-798]] R7-9 | [[MYLA-705]] (the red case, `env`'s case, batch names) | `lib/std/platform_windows.my`, `scripts/windows-runner.py` |
| Website | [[MYLA-799]] R7-10 | [[MYLA-630]] (the skip link, a phone's width, the sizes) | `website/`, `learn/` |
| Docs, skill, CI | [[MYLA-800]] R7-11, last | | `docs/`, `.agents/`, `.github/` |

Order: the checker, lowering, interpreter, HTTP, router and numerics lanes hold the high findings and come first. The HTTP and router lanes share `http.my`, and `rt.my` is touched by the HTTP lane's glances, by [[MYLA-547]]'s record and by the lowering lane's ready ring: order them or split by function. The async place writes of [[MYLA-791]] need a test with a second expectation (the same statement in a function that isn't async), as every runner agrees on the wrong answer. Each package names the range of ids its new tasks take (801 to 884).

Eight decisions are the owner's (section 4 of the review), taken on 2026-11-17 as D255 to D262: as the review recommends, except who may add an operator impl, where any module may implement any trait for any type and two impls of the same signature are an error (D257). They are a folder named `std`, `async` on a trait impl's method and who may add an operator impl ([[MYLA-790]]), an implicit module's cost ([[MYLA-793]], [[MYLA-796]]), a case's time limit ([[MYLA-792]]), `static_files`' policy ([[MYLA-795]]), long paths on Windows ([[MYLA-798]]) and the generated tests' full size ([[MYLA-800]]).

They run in two waves on the 4 CPUs of the machine that integrates them: first the checker, lowering, interpreter, HTTP and Windows lanes, then the parser and loader, router, numerics, XML and docs lanes. The website lane waits: another agent works on the website meanwhile.

Left for later, as before: [[MYLA-433]], [[MYLA-434]], [[MYLA-504]], [[MYLA-530]], [[MYLA-531]], [[MYLA-377]], [[MYLA-317]], [[MYLA-368]], and [[MYLA-885]] (the poller in Myla's terms, the box [[MYLA-716]] left). Part 2 of the review of 9 November, the whole-codebase pass, is still to come.

## Round 7's follow-ups (2026-11-18)

What round 7 left open, grouped by the files it touches so that lanes running side by side merge with few conflicts. Master's x86_64-windows suites and its `windows` job were red after round 7's merges, so the concurrency and Windows lane comes first and is merged on its own. Its causes: a hang under Wine ([[MYLA-759]]) and the last of 20 HTTP requests lost on real Windows ([[MYLA-863]]). The Wine prefix's setup, also part of it, is fixed before the wave (PR #83).

**Wave 1**, five lanes side by side:

| Lane | Tasks | Files | Shares, by function, with |
| --- | --- | --- | --- |
| Concurrency and Windows CI | [[MYLA-759]], [[MYLA-863]], [[MYLA-781]], [[MYLA-861]], [[MYLA-819]]'s Windows part (job objects), [[MYLA-745]] | `lib/std/rt.my` (the executor, `await`), `platform_windows.my` (the heap, the poller), `http.my`'s `serve_with` and `Tally`, `tests/burn` | rt.my with Numerics; platform_windows.my with Linux platform; interp.my's `await` with Interpreter |
| Interpreter and harness | [[MYLA-817]], [[MYLA-818]], [[MYLA-819]]'s Linux part | `selfhost/interp.my`, `harness.my`, `driver.my`, `main.my`, `lib/std/test.my` | interp.my with both others |
| Compiler | [[MYLA-802]], [[MYLA-826]] | `selfhost/checker.my`, `ir_a64.my`; the wasm32 tools' stack (`tools/wasm/`, the website's agent's) | |
| Numerics | [[MYLA-843]], [[MYLA-849]], [[MYLA-850]], [[MYLA-851]] | `lib/std/num.my`, `hash.my`, `json.my`, `scripts/gen_std_linalg.py`; rt.my's float printing; interp.my and lower.my for a caller's position | rt.my |
| Linux platform | [[MYLA-758]], [[MYLA-862]] | `platform.my` and `platform_aarch64.my` made one module over per-architecture call numbers; `process.my` | platform_windows.my's `run_with` |

The concurrency lane is merged on its own as soon as it is done; the other four together after it, the Linux platform last, as it reshapes two whole modules. Each lane's new tasks take ids from its own range of 886 to 925.

**Wave 2**, after wave 1: HTTP and files, [[MYLA-833]] (a slow reader parked), [[MYLA-841]] (where a link leads) and [[MYLA-842]]. Both 833 and 841 need a new primitive, so this lane alone stages the seeds (D207). 841's primitive goes into the one Linux module that wave 1 makes.

Not in a wave: [[MYLA-885]] (the poller in Myla's terms) would rewrite the poller in every platform module, after both platform lanes; [[MYLA-799]] (the website) waits for its agent. The tasks round 7 left in `review` wait for the owner's sign-off.
