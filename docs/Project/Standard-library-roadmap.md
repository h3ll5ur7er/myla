# Standard library roadmap

Candidates for the standard library, for the owner to review, extend and order. The first input was what Advent of Code 2015 to 2021 had to write for itself ([[Project/AoC-2015-2021]], [[MYLA-314]]). The second was the owner's list: streams, stream operations, hashes, encodings, formats, functional operations, data structures and algorithms. Ideas of the agent's own fill the gaps. The rows are planned as tasks in four waves ([[#The plan]]), so that several agents can work on them at once without clashing.

[TOC]

## Reading the table

- **#**: a fixed number to refer to a row by. It doesn't change when the order does.
- **Use**: how often a typical program would reach for it. 0 is never, 10 is every day.
- **Size**: the order of magnitude of the work, tests and docs included. The scale is roughly logarithmic:

  | Size | Work |
  | --- | --- |
  | 0 | Basically free: an hour |
  | 1 | A few hours |
  | 2 | A day |
  | 3 | A few days |
  | 4 | A week |
  | 5 | Two to three weeks |
  | 6 | A month, or it needs a language change first |
  | 7 | Months, and hard to get right (cryptography) |
  | 8 | Half a year |
  | 9 | A year or more (a TLS stack of our own) |
  | 10 | Between your retirement and the heat death of the universe |

- **Needs**: a row (`#n`) or a task that has to come first.
- **Priority**: the suggested order of implementation, 1 first.
- **Task**: the task that implements the row; `–` for a row planned for later. It weighs use against size, puts prerequisites first, and lets cheap rows that many others build on go early.

## What std has today

`std.io` (buffered reading, writing to a descriptor), `std.fs` (whole-file reads and writes, directories), `std.process` (run and capture, a command builder, the environment), `std.num` (exact number parsing and printing), `std.math` (floating-point functions), `std.fmt` (format specs), `std.json` and `std.toml` (parsers, and a JSON printer), `std.time` (a clock), `std.task` (cancellation), `std.slice` (ranges), `std.test` (expectations and temporary directories for tests, D162). There is nothing yet for strings beyond `len`, `chars`, slicing and `StringBuilder`, and nothing for sorting, collections, hashes, encodings, streams or randomness.

## What the language has to settle first

The language decides a few rows. These are tasks, not rows:

- [[MYLA-315]]: a generic function can't build an empty generic value. Until it is fixed, `Set`, `Deque`, `Heap` and the B-tree can't have constructor functions.
- [[MYLA-310]]: `remove` takes time in the map's size, which would make every set and every cache built on a map quadratic.
- [[MYLA-313]]: tuples and structs as map keys. Without it, sets and graph searches over pairs need packed keys.
- [[MYLA-318]]: `<` on strings, `for` over a `str`, and `char - char` make the string helpers read better, but none blocks them.
- D162 brought test functions, so a generic helper is tested by a test function that calls it with concrete types; `#test` cases still can't take a generic function (D116).

Three questions for the owner are worth deciding before the first module is written. They are part of [[MYLA-319]], with three more (names, tests, docs):

1. **Methods or functions.** `s.split(",")` reads like the built-ins and needs `impl str` in `std`. It also needs every program to see those methods without an import: a prelude, like `get` today. A plain `split(s, ",")` from `import std.str` needs neither. The table assumes methods, written "str methods" and "list methods".
2. **Bytes or characters.** Strings are bytes (D21, D42). The table assumes byte-wise operations with ASCII character classes and Unicode left to #10, as Go and Rust do.
3. **Errors.** A `Result` with an error enum per module, as `IoError` is (D129), rather than `Option`.

## Candidates

### Strings and text

| # | Name | Where | What | Use | Size | Needs | Priority | Task |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | String search | str methods | `find`, `rfind`, `find_from`, `contains`, `starts_with`, `ends_with`, `count` on a `str` | 10 | 1 |  | 1 | [[MYLA-321]] |
| 2 | Split and join | str methods | `split(sep)`, `splitn`, `words` (split on whitespace), `lines`, and `join` on a `[str]` | 10 | 1 |  | 2 | [[MYLA-321]] |
| 3 | Trim, case, repeat, pad | str methods | `trim`, `trim_start`, `trim_end`, `strip_prefix`, `strip_suffix`, ASCII `to_upper` and `to_lower`, `repeat(n)`, `pad_start` and `pad_end` | 9 | 1 |  | 3 | [[MYLA-321]] |
| 4 | Replace | str methods | `replace(from, to)`, `replacen` | 8 | 1 |  | 6 | [[MYLA-321]] |
| 5 | Character classes | char methods | `is_digit`, `is_alpha`, `is_alnum`, `is_space`, `is_upper`, `is_lower`, `to_digit(radix)`, `from_digit`, ASCII first | 9 | 0 |  | 4 | [[MYLA-322]] |
| 6 | Number parsing and printing | `std.num` | `parse_int` in a radix and for every width, with a `Result` that says why it failed (today: `Option<int64>`); integers printed in a radix (hex, binary) with a width | 8 | 2 |  | 14 | [[MYLA-331]] |
| 7 | Bytes and strings | `std.bytes` | a `str` from `[uint8]` and back, UTF-8 validation, a `char` to and from its UTF-8 bytes | 7 | 1 |  | 15 | [[MYLA-329]] |
| 8 | Scanner | `std.text` | a cursor over a `str` for hand-written parsers: `peek`, `next`, `take_while`, `skip_space`, `expect`, `int`; and `ints(line)`, every integer in a line (AoC's most used helper after `split`) | 6 | 2 |  | 32 | [[MYLA-341]] |
| 9 | Text layout | `std.text` | word wrap, aligned columns for tables, indent and dedent | 4 | 2 |  | 58 | [[MYLA-341]] |
| 10 | Unicode | `std.unicode` | properties and case mapping beyond ASCII, grapheme clusters, NFC normalisation; the tables are large | 3 | 6 |  | 65 | – |

### Numbers

| # | Name | Where | What | Use | Size | Needs | Priority | Task |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 11 | Integer helpers | `std.int` | `abs`, `min`, `max`, `clamp`, `sign`, `pow`, `gcd`, `lcm`, Euclidean `div` and `mod` (never negative), for every width; `std.math` has these for floats only | 9 | 1 |  | 5 | [[MYLA-322]] |
| 12 | Checked and wrapping arithmetic | `std.int` | `checked_add` (an `Option`), `wrapping_*`, `saturating_*`, `overflowing_*`; whatever [[MYLA-311]] decides, these are part of it | 6 | 2 | [[MYLA-311]] | 28 | [[MYLA-322]] |
| 13 | Modular arithmetic | `std.int` | `mulmod` without overflow, `powmod`, `modinv` | 3 | 1 |  | 47 | [[MYLA-322]] |
| 14 | Big integers | `std.bigint` | arbitrary precision: add, subtract, multiply, divide with remainder, `pow`, parse, print; `std.num` already has the internals for its exact float conversions | 4 | 4 |  | 50 | [[MYLA-345]] |
| 15 | Random numbers | `std.random` | a seeded generator (PCG or xoshiro), seeds from the OS (a new primitive: `getrandom`, WASI's `random_get`), ranges, `shuffle`, `choice` | 7 | 3 | a primitive per target | 23 | [[MYLA-337]] |

### Lists and functional operations

| # | Name | Where | What | Use | Size | Needs | Priority | Task |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 16 | List building | list methods | `filled(n, v)`, a list of a range, `reversed`, `concat`, `extend`, `insert`, `remove_at`, `swap`, `truncate`, `dedup` | 9 | 2 |  | 7 | [[MYLA-323]] |
| 17 | Higher-order list operations | list methods | `map`, `filter`, `fold`, `reduce`, `any`, `all`, `find`, `position`, `count`, `sum`, `min_by`, `max_by`, `flat_map`, `zip`, `enumerate`, `chunks`, `windows`; methods on `[T]` (D144) taking closures | 10 | 2 |  | 8 | [[MYLA-323]] |
| 18 | Sorting | list methods | a stable `sort`, `sort_by(less)`, `sort_by_key`, `is_sorted`; an unstable sort for speed | 9 | 2 |  | 9 | [[MYLA-323]] |
| 19 | Binary search | list methods | `binary_search`, `lower_bound`, `upper_bound`, `partition_point` on a sorted list | 7 | 1 |  | 16 | [[MYLA-323]] |
| 20 | Option and Result combinators | `Option`, `Result` methods | `map`, `and_then`, `or_else`, `unwrap_or`, `unwrap_or_else`, `ok_or`, `map_err`, `is_some`, `is_none`, `is_ok`, `is_err`, `expect` | 9 | 2 |  | 10 | [[MYLA-324]] |
| 21 | Iterators | `std.iter` | an `Iterator` trait (`next() -> Option<T>`), lazy adapters, `for` over one: no list built for each step | 7 | 6 | a language decision: `for` over a trait | 53 | [[MYLA-353]] |
| 22 | Combinatorics | `std.combin` | permutations, combinations, cartesian products, `next_permutation` | 4 | 1 |  | 43 | [[MYLA-323]] |

### Collections and algorithms

| # | Name | Where | What | Use | Size | Needs | Priority | Task |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 23 | Map helpers | map methods | `get_or(k, default)`, `update(k, default, f)`, `values()`, `items()`, a counter (how often each element occurs), `merge` | 8 | 1 |  | 11 | [[MYLA-324]] |
| 24 | Set | `std.set` | `Set<T>`: `insert`, `remove`, `contains`, `union`, `intersection`, `difference`, from a list; primitive elements first, tuples with [[MYLA-313]] | 9 | 2 | [[MYLA-310]], [[MYLA-315]] | 17 | [[MYLA-330]] |
| 25 | Deque | `std.deque` | `Deque<T>`, a ring buffer: push and pop at both ends, indexing; it is the queue | 8 | 2 | [[MYLA-315]] | 18 | [[MYLA-330]] |
| 26 | Priority queue | `std.heap` | a binary heap over `Ord`, min or max, or keyed by a priority | 7 | 2 | [[MYLA-315]] | 19 | [[MYLA-330]] |
| 27 | Sorted map and set | `std.btree` | a B-tree with ordered iteration, range queries, `first`, `last` | 5 | 4 | [[MYLA-315]] | 48 | [[MYLA-343]] |
| 28 | Bit set | `std.bitset` | fixed and growable bit sets, `popcount`, set operations | 5 | 2 |  | 41 | [[MYLA-342]] |
| 29 | Union-find | `std.unionfind` | disjoint sets with path compression and union by rank | 4 | 1 |  | 45 | [[MYLA-342]] |
| 30 | Grid | `std.grid` | a 2D array with width and height: in-bounds checks, 4 and 8 neighbours, read from text, printed | 5 | 2 |  | 39 | [[MYLA-342]] |
| 31 | Graph search | `std.graph` | BFS, DFS, Dijkstra, A*, topological sort, connected components, over a neighbour function | 5 | 3 | #25, #26 | 40 | [[MYLA-342]] |
| 32 | Caches | `std.cache` | an LRU cache; a memoising wrapper around a map | 3 | 2 |  | 61 | [[MYLA-404]] |

### Hashes, checksums, encodings, cryptography

| # | Name | Where | What | Use | Size | Needs | Priority | Task |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 33 | Fast hashes | `std.hash` | FNV-1a and a fast 64-bit hash (wyhash or xxHash64) of a `str` or bytes, hash combining: what a `Hash` trait ([[MYLA-313]]) would build on | 6 | 1 |  | 22 | [[MYLA-327]] |
| 34 | Checksums | `std.hash` | CRC-32 and Adler-32 (gzip, zlib, PNG and zip need them) | 5 | 1 |  | 35 | [[MYLA-327]] |
| 35 | MD5 and SHA-1 | `std.digest` | one-shot and incremental, as bytes and as hex; legacy but everywhere (Git's object ids, ETags, AoC); tuned, since AoC's MD5 dominated its slowest days | 6 | 2 |  | 20 | [[MYLA-328]] |
| 36 | SHA-2 and HMAC | `std.digest` | SHA-256, SHA-512, HMAC; one-shot and incremental | 6 | 2 |  | 21 | [[MYLA-328]] |
| 37 | Hex and Base64 | `std.encoding` | encode and decode, Base64 in the standard and the URL-safe alphabet | 8 | 1 |  | 13 | [[MYLA-329]] |
| 38 | URLs | `std.url` | percent-encoding, query strings, parsing and building a URL | 5 | 2 |  | 44 | [[MYLA-329]] |
| 39 | Cryptography | `std.crypto` | authenticated encryption (ChaCha20-Poly1305, AES-GCM), X25519, Ed25519, constant-time comparison; checked against the published vectors, with side channels in mind | 4 | 7 | #15, #36 | 66 | – |
| 40 | TLS | `std.tls` | a TLS 1.3 client | 4 | 9 | #39, #47 | 67 | – |

### Streams and I/O

| # | Name | Where | What | Use | Size | Needs | Priority | Task |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 41 | Stream traits and memory streams | `std.io` | `Read`, `Write` and `Seek` traits; buffered readers and writers generic over them; a memory stream (bytes and a cursor); `copy`. Today's `Reader` becomes one. Without references, a stream lives in a `var` and an adapter owns the stream it wraps (`GzipReader<R: Read>`) | 8 | 4 |  | 26 | [[MYLA-338]] |
| 42 | File streams | `std.fs` | `open` with modes (read, write, append, create, truncate), reads and writes at the cursor, `seek`, `len`, `flush`; metadata (size, modification time, permissions); files bigger than memory. New primitives on each target (`open`, `read`, `write`, `lseek`, `close`, `fstat`) | 8 | 4 | #41, primitives per target | 27 | [[MYLA-339]] |
| 43 | Paths | `std.path` | `join`, `parent`, `file_name`, `stem`, `extension`, `normalize`, `is_absolute`, `relative`; string code only | 9 | 1 |  | 12 | [[MYLA-326]] |
| 44 | Directory walks and globs | `std.fs`, `std.glob` | a recursive walk; glob matching (`*`, `?`, `**`, `[...]`) | 6 | 2 |  | 33 | [[MYLA-326]] |
| 45 | Temporary files and directories | `std.fs` | unique names under `$TMPDIR`, removed by the caller; `std.test.temp_dir` (D162) moved onto them | 5 | 1 |  | 34 | [[MYLA-339]] |
| 46 | Streaming processes | `std.process` | spawn with pipes: write the child's input and read its output as it comes (today the output is captured whole); `wait`, `kill`, pipelines | 6 | 4 | #41 | 37 | [[MYLA-340]] |
| 47 | Sockets | `std.net` | TCP clients and servers, UDP, addresses, name lookup; async on the reactor. wasm32 on WASI has none (`Unsupported`) | 7 | 6 | #41, primitives per target | 42 | [[MYLA-346]] |
| 48 | HTTP | `std.http` | an HTTP/1.1 client and server over #47: requests, headers, chunked bodies; HTTPS needs #40 | 6 | 6 | #47 | 54 | [[MYLA-347]] |
| 49 | Decompression | `std.compress` | DEFLATE decompression, with the gzip and zlib containers, as a stream | 5 | 4 | #34, #41 | 46 | [[MYLA-344]] |
| 50 | Compression | `std.compress` | the DEFLATE compressor: LZ77 matching, fixed and dynamic Huffman codes, a level from fast to small | 4 | 5 | #49 | 55 | [[MYLA-352]] |
| 51 | Archives | `std.archive` | tar read and write, zip read | 3 | 3 | #49 | 62 | [[MYLA-352]] |

### Formats

| # | Name | Where | What | Use | Size | Needs | Priority | Task |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 52 | CSV | `std.csv` | RFC 4180 read and write (quotes, escapes, CRLF), rows as `[str]` or mapped by the header, streaming over #41 | 6 | 2 |  | 29 | [[MYLA-332]] |
| 53 | JSON, more | `std.json` | a pretty printer, typed getters (`as_int`, `as_str`) and path access, a builder; `std.json` already parses and prints | 7 | 2 |  | 24 | [[MYLA-332]] |
| 54 | INI | `std.ini` | read and write: sections, keys, comments | 4 | 1 |  | 38 | [[MYLA-332]] |
| 55 | TOML writer | `std.toml` | writing TOML (`std.toml` parses it), e.g. for the project tool's manifest edits: done, `to_string` round-trips what `parse` reads | 3 | 2 |  | 59 | [[MYLA-402]] |
| 56 | XML | `std.xml` | a non-validating parser (elements, attributes, text, entities, CDATA, comments) to a tree and as a pull reader, a writer with escaping; no DTD and no namespaces at first | 5 | 4 |  | 49 | [[MYLA-348]] |
| 57 | YAML | `std.yaml` | the safe subset: block and flow maps and lists, scalars, multi-line strings, comments; no anchors and no tags. The whole specification would be an 8 | 5 | 4 |  | 51 | [[MYLA-349]] |
| 58 | Serialisation by derive | compiler, `std.json` | `#derive(Json)` (or a serialisation trait) between structs and JSON or TOML, generated as `#derive(Eq)` is | 7 | 6 | a language decision | 56 | [[MYLA-354]] |
| 59 | Regular expressions | `std.regex` | RE2-style, linear time, no backreferences: match, find, find all, captures, replace, split | 8 | 5 |  | 31 | [[MYLA-335]] |

### Programs

| # | Name | Where | What | Use | Size | Needs | Priority | Task |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 60 | Command-line arguments | `std.args` | flags, options, positional arguments, subcommands and generated help; the tools in Myla each parse theirs by hand | 7 | 3 |  | 25 | [[MYLA-333]] |
| 61 | Date and time | `std.time` | UTC civil time from the clock, durations, ISO 8601 and RFC 3339 parsing and printing, weekdays; time zones (tzdata) later | 7 | 3 |  | 30 | [[MYLA-334]] |
| 62 | Logging | `std.log` | levels, to the standard error, a timestamp, the level from an environment variable | 5 | 1 |  | 36 | [[MYLA-334]] |
| 63 | Terminal | `std.term` | ANSI colours and styles, `is_tty`, the terminal's size, raw mode for line editing (the REPL) | 4 | 2 |  | 52 | [[MYLA-350]] |
| 64 | Signals | `std.signal` | SIGINT and SIGTERM handled, for a clean shutdown, as an async event | 3 | 3 | primitives per target | 64 | [[MYLA-350]] |
| 65 | UUIDs | `std.uuid` | v4 (random) and v7 (ordered by time), parse and print | 3 | 1 | #15 | 60 | [[MYLA-337]] |
| 66 | Concurrency utilities | `std.task` | channels between tasks, a worker pool, a timeout around an await, waiting for the first of several | 6 | 4 |  | 57 | [[MYLA-351]] |
| 67 | Benchmarking | `std.bench` | time a closure over repeated runs; report the minimum and the median: done, `run`, `run_n`, `run_for`, `black_box` | 4 | 1 |  | 63 | [[MYLA-403]] |
| 68 | Test helpers | `std.test` | `expect`, `expect_eq`, `expect_ne`, `fail`, `temp_dir`, `program`: done (D162) | 9 | 2 |  | – | [[MYLA-304]] |

## The suggested order

1. **Everyday basics** (priorities 1 to 16): String search (#1), Split and join (#2), Trim, case, repeat, pad (#3), Character classes (#5), Integer helpers (#11), Replace (#4), List building (#16), Higher-order list operations (#17), Sorting (#18), Option and Result combinators (#20), Map helpers (#23), Paths (#43), Hex and Base64 (#37), Number parsing and printing (#6), Bytes and strings (#7), Binary search (#19). All are size 0 to 2, use 7 or more, and plain Myla over what exists. They cover most of what AoC's `text.my`, `num.my` and `sort.my` held.
2. **Collections and hashes** (17 to 25): Set (#24), Deque (#25), Priority queue (#26), MD5 and SHA-1 (#35), SHA-2 and HMAC (#36), Fast hashes (#33), Random numbers (#15), JSON, more (#53), Command-line arguments (#60). The collections come after [[MYLA-315]] and [[MYLA-310]].
3. **Streams, files and the middle tier** (26 to 41): Stream traits and memory streams (#41), File streams (#42), Checked and wrapping arithmetic (#12), CSV (#52), Date and time (#61), Regular expressions (#59), Scanner (#8), Directory walks and globs (#44), Temporary files and directories (#45), Checksums (#34), Logging (#62), Streaming processes (#46), INI (#54), Grid (#30), Graph search (#31), Bit set (#28). The stream traits come first, because file streams, process pipes, CSV over streams and decompression all build on them.
4. **Networks and larger formats** (42 to 54): Sockets (#47), Combinatorics (#22), URLs (#38), Union-find (#29), Decompression (#49), Modular arithmetic (#13), Sorted map and set (#27), XML (#56), Big integers (#14), YAML (#57), Terminal (#63), Iterators (#21), HTTP (#48).
5. **Later** (55 to 67): Compression (#50), Serialisation by derive (#58), Concurrency utilities (#66), Text layout (#9), TOML writer (#55), UUIDs (#65), Caches (#32), Archives (#51), Benchmarking (#67), Signals (#64), Unicode (#10), Cryptography (#39), TLS (#40). Cryptography and TLS come last on purpose. They are hard to get right, and a wrong one is worse than none.

## The plan

[[MYLA-314]] is the umbrella. The work runs on three tracks:

- **Library lanes:** modules in Myla under `lib/std/`, one task each. Each task owns its files, so many of them run at once.
- **The compiler track:** tasks that change `selfhost/`. They run one at a time, because they share the checker and the lowering. MYLA-310 is the exception: it changes only the map routines (`std.rt`, the lowering's `map_remove`, the interpreter's maps), so it can run beside MYLA-320.
- **The platform track:** tasks that add primitives. Each changes the three platform modules, the primitive tables, the three backends and the interpreter, and needs a seed staging commit (D156). They run one at a time.

| Wave | Library lanes, in parallel | Compiler track | Platform track |
| --- | --- | --- | --- |
| 1 Foundations | [[MYLA-325]] first (the integrator), then [[MYLA-321]], [[MYLA-322]], [[MYLA-323]], [[MYLA-324]] | [[MYLA-319]] (the owner's decision), then [[MYLA-320]]; [[MYLA-310]] beside it | [[MYLA-336]] |
| 2 Collections, hashes and formats | [[MYLA-326]], [[MYLA-327]], [[MYLA-328]], [[MYLA-329]], [[MYLA-331]], [[MYLA-332]], [[MYLA-333]], [[MYLA-334]], [[MYLA-335]], [[MYLA-338]]; [[MYLA-330]] once MYLA-310 and MYLA-315 are in | [[MYLA-315]], then [[MYLA-313]] (after MYLA-327), then [[MYLA-318]] | |
| 3 Streams and the middle tier | [[MYLA-337]], [[MYLA-339]] and [[MYLA-340]] (after MYLA-336 and MYLA-338), [[MYLA-341]], [[MYLA-342]] (after MYLA-330), [[MYLA-343]], [[MYLA-344]], [[MYLA-345]] | [[MYLA-353]] (a decision); the fixes the lanes needed, [[MYLA-360]], [[MYLA-367]], [[MYLA-374]], [[MYLA-375]] | [[MYLA-378]] (what the lanes found missing) |
| 4 Networks and larger formats | [[MYLA-347]] (after MYLA-346), [[MYLA-348]], [[MYLA-349]], [[MYLA-351]], [[MYLA-352]], [[MYLA-354]] (a decision) | | [[MYLA-346]], then [[MYLA-350]] |
| 5 Small modules (2026-11-09) | [[MYLA-402]] (#55), [[MYLA-403]] (#67), [[MYLA-404]] (#32) | [[MYLA-396]], [[MYLA-359]] (check time) | |
| Later | No tasks yet: #10, #39, #40 | | |

A wave's lanes start once the previous wave's pull request is merged. A lane whose task needs nothing may start earlier, while an agent is free: MYLA-327, MYLA-328, MYLA-329, MYLA-335 and MYLA-338 need nothing at all.

Lanes that would clash are in different waves, or one after the other in one: MYLA-332 and MYLA-354 (both on `std.json`); MYLA-339 and MYLA-338 (`std.fs` uses the stream traits); MYLA-344 and MYLA-352 (`std.compress`); every task of the platform track.

### Working in parallel

The rules for a lane, which an agent is given with its task:

1. Read `AGENTS.md`, the `myla` skill, the task, and this section. Work in a worktree of your own, on a branch `stdlib/MYLA-<n>` from the wave's branch.
2. Change only the files the task owns, plus the module's row in the index table on [[Language/Standard-library]]. A helper you need from a module of another lane that doesn't exist yet is written privately in your own file and named on the task. The integrator replaces it with the other module's.
3. Import what you use explicitly, even a module that [[MYLA-320]] makes implicit: the modules of `std` don't get the implicit imports.
4. Never run `scripts/update-seed.sh`, and never commit `bootstrap/seed.s`, `bootstrap/seed-aarch64.s` or `selfhost/embedded_std.my`. Run `scripts/bootstrap.sh` to test with your module embedded.
5. Write the tests first (soft TDD) and see them fail: `myla test lib/std/<m>.my`, then with `--native`. A module with I/O also runs with `--target aarch64` and `--target wasm32`.
6. When done, self-review the diff, tick the task's boxes with evidence (test output, measurements), set it to `review`, and hand the branch to the integrator.

The integrator, one agent per wave:

1. Merges the lanes' branches into the wave's branch in task order, and resolves the index rows.
2. Replaces the private helpers with the modules that now exist.
3. Runs the whole suite (`scripts/test.sh`).
4. Makes the one seed commit (`scripts/update-seed.sh`, D156) and opens one pull request for the wave.

Compiler and platform tasks have their own pull requests, each with its seed commit, and the wave's branch merges master after each one.

## Left out

- **Graphics, audio, GUI and databases.** These are packages for the project tool ([[Architecture/Project-tool]]), not std.
- **A full YAML, XML Schema or HTTP/2.** Each would be a size 8. The subsets above cover the common use.
- **Dynamic dispatch for streams** (`[Box<dyn Read>]`). Myla has no trait objects ([[Language/Methods-and-traits]]). Generic adapters and an enum of known stream kinds cover the cases seen so far.
