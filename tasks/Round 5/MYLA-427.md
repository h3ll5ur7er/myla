---
id: MYLA-427
title: "P13 Documentation and the board"
type: chore
status: done
priority: medium
labels: [docs, board, round-5]
---
Work package P13 of [[Project/Review-2026-11-09]] (wave A2), with round 4's additions from [[Project/Review-2026-11-10]]. Files: `docs/`, `tasks/`. The decisions themselves (D178 to D187) and the sign-offs were recorded with the reviews.

- [x] The stale sentences of §3.3: `Types.md:42` (tuples can't be compared), `Heap.md:89`, `Option.md`'s lambda note ([[MYLA-324]]), `Int.md` and `Char.md` line 3, the Set, Deque and Heap pages on MYLA-353 and iterators ([[MYLA-330]]), `Url` and `Eq`
- [x] [[Project/Known-issues]]: remove the 20 tasks that are done
- [x] Undocumented `pub` items (`fmt.spec_need`, `io.errno_text`, methods on a dozen pages); runnable blocks for Fmt, Rt, Slice, Test and the four pages [[MYLA-325]] names
- [x] The Regex, Time and Io pages with the reference part first (after wave A2's merge, in round 5's follow-up)
- [x] Evidence counts in task files and pages that later refactors changed
- [x] D178 in [[Language/Methods-and-traits]] with the call-site error once [[MYLA-417]] builds it
- [x] D179 in [[Development/Conventions]]: library editors run `myla test` on the module they changed
- [x] D180: Net.md's line-protocol example and the warning that `buffered(s)` blocks its worker: written by [[MYLA-419]] (P5), with the async line reader it uses (`net.line_reader`, a tested block in [[Language/Standard-library/Net]])
- [x] Io.md, Fs.md and Process.md: performance sections as current numbers, not histories of `read_str` measurements (after wave A2's merge, in round 5's follow-up)

## Evidence

Each claim was checked against the code on `95785ab` (wave A1 integrated) before its sentence changed, interpreted and natively (`build/myla run`, `build/myla build`):

- **§3.3's stale sentences.**
  - `Types.md:42`: `(1, "a") == (1, "a")` prints `true` and a `[(int, int): str]` map works, both runners (D163). `(1, 2) < (1, 3)` is still an error, so the page now says tuples have no order.
  - `Heap.md`: a `Heap<str>` gives `apple` before `pear`, and a generic `impl<T: Ord> Ord for Rev<T>` with `<`, and `impl<T> Eq for Box<T>` with `==`, link and print the interpreter's answer natively. [[MYLA-367]] fixed MYLA-330's bug 1; `str` has been `Ord` since [[MYLA-318]].
  - `Option.md`: `o.map((n) => n * 2)`, `o.and_then((n) => …)`, `r.map_err((s) => s.len())` and `apply(3, (x) => x + 1)` check and print `8 5 4` and `err 3` on both runners ([[MYLA-356]]).
  - `Int.md` and `Char.md`: the modules are implicit since [[MYLA-320]]. Int's block no longer imports `std.int`.
  - `Set.md`, `Deque.md`: `Iterator<T>` exists (D171, [[MYLA-353]]), but neither type implements it yet (that is [[MYLA-425]]'s `iter()`). The sentences say so instead of naming a missing trait. Heap's page never mentioned MYLA-353.
  - `Url.md`: `Option` is `Eq` since [[MYLA-379]], so the reason given was wrong. `Url` itself still isn't `Eq` (`operator '==' is not defined for 'url.Url'`). A copy of the library with `#derive(Eq, Hash)` on it prints `true` on both runners. Filed as [[MYLA-488]], since `url.my` is P8's.
  - Xml.md's wasm32 sentence is P10's ([[MYLA-424]]).
- **Known issues.** 22 of the page's tasks were `done`: 183, 221, 230, 250, 284 to 287, 289 to 295, 297, 298, 300, 301, 310, 311 and 315. The review counted 20. Their lines went. MYLA-313 is in `review`, but its sentence ("tuples have no `==` …") no longer holds, so it went too. MYLA-296's line now names what is open in it (the native timer lock; the interpreter's memory per task is fixed). MYLA-299's names the tutorial. New lines cover round 5's open tasks that aren't wave A2 packages: [[MYLA-429]], [[MYLA-430]], [[MYLA-432]], [[MYLA-433]], [[MYLA-434]], [[MYLA-435]], [[MYLA-436]], [[MYLA-440]], [[MYLA-441]], [[MYLA-448]], [[MYLA-449]] and [[MYLA-488]], with a Standard library section. `#test` coverage re-measured with `scripts/test_coverage.py`: 67 % (1,402 of 2,107), on the page and on [[Development/Testing]], which said 80 % (1,030 of 1,286). The `fib(30)` figure stays MYLA-317's: on this loaded machine the interpreter took 4.8 to 6.1 s and native code 6 ms, which is no measurement to publish.
- **Undocumented `pub` items.** A scan compared each module's `pub` names, and the methods of its public types, with the words of its page. It found `fmt.spec_need` and `io.errno_text` (rows added) and `Regex.replacen` (a row: `replace` and `replace_all` are `replacen` with 1 and -1). It also found helper methods on twelve pages: Archive, Bigint, Compress, Csv, Digest, Http, Io, Net, Process, Regex, Term and Xml. Each page now names them in one sentence as steps that are public only because a method can't be private yet ([[MYLA-433]]), as Deque's page already did for `grow`. After the edits the scan finds nothing outside std.rt. std.rt's 109 unnamed functions are "not for programs", and its page lists them by what they are behind.
- **Runnable blocks.** Fmt (a `Format` impl through `fmt.pad`, plus `parse_spec` and `spec_need`), Slice (`range_of`, `take` and `str_whole` beside the slices they compute), Test (a test function with `temp_dir`, `expect_eq`, `expect_ne` and `expect`; `myla test` gives `PASS  saves_one_word_a_line` interpreted and `--native`) and Rt (operations a native build runs through std.rt, each function linked in the binary, `nm`). Those are the four pages without a runnable block that MYLA-325 named. Each prints its `// output:` interpreted and natively. `python3 -m unittest tests.burn.test_doc_blocks tests.burn.test_lsp`: `Ran 169 tests … OK`.
- **Counts that refactors lowered.** Every module's cases were counted with `build/myla test lib/std/<m>.my --stdlib lib --list` and compared with the counts in task files. Where a later refactor took cases away (found with each commit's added and removed `#test` lines), the stated count now gives today's count and the cause:
  - [[MYLA-376]], [[MYLA-359]] and [[MYLA-396]]: std.int's 2,042 cases are 1,826 since MYLA-395 (216).
  - [[MYLA-313]]: std.hash's 95 cases are 65 since MYLA-359 (30 to std.checksum).
  - [[MYLA-379]]: bigint 140 is 138 (MYLA-396).
  - [[MYLA-369]]: io 26 is 24 (MYLA-399).
  - [[MYLA-342]]: bitset 73 is 67.
  - [[MYLA-352]]: compress 139 is 136 and archive 86 is 83 (MYLA-376).

  Counts that later work raised are history and stay. The pages Archive (86, now 83), Compress (139, now 136), Http (161, now 156) and Xml (98, now 89) are left to P9, P8 and P10, whose own new cases change those numbers again. The integrator should check them after the merge.
- **D178.** [[Language/Methods-and-traits#methods]] already described the call-site error [[MYLA-417]] built, and the corpus has it (`type_method_beside_a_function_field.my`). The page now quotes the declaration error and the field's help as `build/myla check` prints them ("… holds a function: a call '.on(…)' would mean either", help "rename the method or the field; …"; "… not a function: read it without '()'"). Round 4's other P13 items were already in place: D178's row, D45's note, D170's dated clause, D179 for lazy parsing, and the two stale sentences of question 1.
- **D179.** [[Development/Conventions]] already has the rule (`build/myla test lib/std/<module>.my --stdlib lib` after changing a module), from MYLA-416.
- All 42 wiki links added resolve to a page, a file or a task.
- Suites: `scripts/test.sh fast` `Ran 829 tests … OK (skipped=3)`. The full `scripts/test.sh` wasn't run: the package changes no code, only `docs/` and `tasks/`, and the tests that read either are `test_doc_blocks`, `test_lsp` and the corpus tests of the fast suite.

## Evidence of the follow-up (2026-11-11)

The two items left open, on `bccc624` (round 5 with D188 and D189):

- **Reference first.** Paragraphs moved, not rewritten, apart from a lead-in sentence for a new table and the numbers of the next item.
  - [[Language/Standard-library/Io]]: the reference (writing, Reading with the async reads, Streams with the traits, this module's streams, any stream, a stream of your own) comes first, then a new "How it works" with the paragraphs on linear reads, short reads' cells, the descriptors' byte primitives and `copy`'s pieces, then "Speed". The sentence on a failed read in the middle of a line stayed in Reading, as reference.
  - [[Language/Standard-library/Time]]: "How it works" (the day counting, the cases that check it and the wall clock primitive) moved from inside DateTime to the end, after Errors, with the sentence on the 2000 durations checked against Go.
  - [[Language/Standard-library/Regex]] already had the reference first. `RegexError` and `ErrorKind` moved from the functions' table to an "Errors" section after "Bytes and UTF-8", before "How it matches", as the Http, Compress and Time pages have it.
  - Anchors other pages link to (`Io#streams`, `Io#speed`, `Fs#descriptor-and-entropy-primitives`, `Process#children-as-streams`, `Process#process-primitives`) are unchanged. A scan of every `[[…]]` in the five pages and the task files that link to them finds a page, task, file or heading for each, and only the false hits `[[:alpha:]]` and `[[:^alpha:]]` inside Regex's code. `python3 -m unittest tests.burn.test_doc_blocks`: `Ran 3 tests … OK`.
- **Current numbers.** Every case the three sections cite, re-measured natively on this container (4 cores of a Xeon at 2.1 GHz, shared with five other lanes: load 3.5 to 5), the best of 16 runs in two sets, by a program outside the suite (50 MB of random lines of up to 120 bytes, 819,831 lines; a 256 MiB file of random bytes; 8 and 16 MiB lines). The histories of `read_str` measurements are gone; what explains a design choice stays, dated: the quadratic reads before MYLA-420, the short reads' cells on wasm32, the conversion step D177 removed (481 ms against 111 ms for 4 GiB), the copying pipeline before MYLA-378 (918 to 2,187 ms). `copy`'s 64 KiB was measured again against 4, 16 and 128 KiB with copies of the library: 380, 239, 159 and 197 ms for the 256 MiB file to a new file, 51, 38, 34 and 35 ms to `/dev/null`. Selected numbers: `stdin().read_line()` over the 50 MB 78 ms (the page said 75 and 131 to 133), 4 GiB through two `File`s 82 ms at 11.4 MB resident, as for 1 MiB and 1 GiB, a `ChildStdout` of 256 MiB 107 ms (a shell's `head | cat` 68), the pipeline through `wc -c` 127 ms (a shell's 93), interpreted 2 MB of lines 4.4 s (the page said 6.67 to 6.80).
- **Suites** (lane F of the follow-up, on `bccc624`): `scripts/test.sh fast` `Ran 848 tests … FAILED (failures=1, skipped=3)`, the failure `test_embedded_std` (expected until the seed commit); `tests.burn.test_time` `Ran 13 tests … OK`; the full `scripts/test.sh` `Ran 1517 tests … FAILED (failures=2, skipped=338)`: `test_embedded_std` again and `test_selfhost_codegen.test_children_run_in_parallel`, which asks four children for 1.5 times the wall time in CPU time and got 1.08 s of CPU in 1.36 s at a load of 6.7 on 4 cores; alone at that load it fails the same way, and nothing in this lane touches the runtime or code generation.

## Review 2026-11-12

Signed off in [[Project/Review-2026-11-12]], with a follow-up in [[MYLA-554]]: `Bitset.md` and `Grid.md` still cite [[MYLA-353]]; the coverage figure (63 percent now); seven public helper methods not on their pages.
