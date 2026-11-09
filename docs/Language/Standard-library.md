# Standard library

Myla has built-in functions known to the checker, and a small standard library written in Myla under [[lib/std/io.my|lib/std/]]. Both work without libc: natively they rest on the platform layer `std.platform`, raw Linux system calls on x86-64 and aarch64 and WASI's imports on wasm32 ([[Architecture/Native-backend]]), and so does the interpreter, which is a native program itself. What a target lacks shows as an error of its own, `Unsupported` (D129, D132): on wasm32 `run`, `run_async` and `command(…).run()` fail with `SpawnError.Unsupported`, as there are no processes. What each target can do (processes, suspending input, the file system it sees, the working directory) is on [[Language/Targets]].

[TOC]

## Built-in functions

These names are reserved: no declaration may reuse them. The ones on a receiver are methods only ([[MYLA-221]]).

| Function | Signature | Notes |
| --- | --- | --- |
| `print(x)` | one integer, float, `char`, `bool` or `str`, or a value whose type implements `Format` (D159) | Writes the value and a newline to stdout |
| `x.len()` | list, map, `str` or `StringBuilder` → `int` | A method; strings and builders: bytes |
| `xs.push(v)`, `xs.pop()` | list | Methods; need a `var` place |
| `m.contains(k)`, `m.keys()`, `m.remove(k)` | map | Methods; `remove` needs a `var` place |
| `s.chars()` | `str` → `[char]` | A method |
| `format(fmt, args…)` | → `str` | `fmt` is a literal; see [[Language/Collections-and-strings]] |
| `StringBuilder()`, `StringBuilder(capacity)`, `sb.append(s)`, `sb.append(s, start, end)`, `sb.append_byte(b)`, `sb.append_char(c)`, `sb.build()` | | Methods but `StringBuilder()`; `append(s, start, end)` adds the bytes `s[start..end]` ([[Language/Collections-and-strings]]) |
| `assert(cond[, msg])`, `panic(msg)`, `unreachable()` | | See [[Language/Attributes-and-testing]] |

The low-level primitives `__write`, `__read`, `__write_bytes`, `__read_bytes` (the same with a `[uint8]`, D177), `__poll`, `__exit`, `__args`, `__read_file`, `__write_file`, `__list_dir`, `__mkdir`, `__stat`, `__getcwd`, `__getenv`, `__sqrt`, `__f64_bits`, `__f64_from_bits`, `__unlink`, `__rmdir`, `__rename`, `__io_errno`, `__run`, `__run_stderr`, `__run_exit_code`, `__run_signal`, `__run_errno` and `__task_cancelled`, and the primitives behind `std.time`, `std.task`'s timers, `std.process`'s child processes, `std.net`'s sockets, `std.term`'s terminal and `std.signal`'s signals (`__clock_ns`, `__sleep`, `__spawn`, `__sock_open`, `__term_raw`, `__signal_listen`, …) exist for the standard library; call the `std` functions instead. A call of one from a program outside the standard library compiles, with the warning `primitive` (D100, [[MYLA-186]]): it is for code that knows what it does, such as a new std function in the making, which says so with `#allow(primitive)` or `#allow(primitive(__poll))` (D161, [[Language/Attributes-and-testing#warnings-and-allow]]).

## Modules

One page per module (D164). A new module adds its row here.

The conventions (D164): operations on built-in types are methods (`s.split(",")`, `xs.sorted()`), and `std.str`, `std.char`, `std.int`, `std.list`, `std.option` and `std.map` are seen by every program without an import, and `std.hash`, whose methods and impls the `Hash` trait builds on (D163, D166, [[MYLA-313]]) ([[MYLA-320]], [[Language/Modules#implicit-imports]]: their methods, not their functions, which need an import; not in the modules of `std`, which import what they use); everything else is a function of its module (`path.join(a, b)`). Strings are bytes and character classes ASCII. A function that can fail returns a `Result` with its module's error: a bare enum when the variants carry different data, a struct with a `kind` enum when every error has the same position (D168). A map keyed by a type parameter writes `T: Eq + Hash` (D167).

| Module | Page | Holds |
| --- | --- | --- |
| `std.io` | [[Language/Standard-library/Io]] | Writing to a descriptor, the buffered `Reader`, async reads; the stream traits `Read`, `Write`, `Seek`, memory streams, `Buffered`, `BufferedWriter`, `copy` |
| `std.fs` | [[Language/Standard-library/Fs]] | Whole-file reads and writes, `File` streams (`Read`, `Write`, `Seek`), metadata, directories, temporary files and directories, `IoError` |
| `std.path` | [[Language/Standard-library/Path]] | Paths as strings: `join`, `parent`, `file_name`, extensions, `normalize`, `relative` |
| `std.glob` | [[Language/Standard-library/Glob]] | Glob patterns (`*`, `?`, `**`, sets), directory walks, `glob` |
| `std.process` | [[Language/Standard-library/Process]] | Arguments, the environment, exit, running programs (`run`, `command`), children streamed through pipes (`spawn`, `Child`, `pipe`) |
| `std.net` | [[Language/Standard-library/Net]] | TCP and UDP sockets (`listen`, `connect`, `TcpStream` a `Read` and `Write`, `udp_bind`), their async forms on the reactor, `IpAddr` and `SocketAddr` parsed and printed, name lookup through the hosts file and DNS |
| `std.http` | [[Language/Standard-library/Http]] | An HTTP/1.1 client (`fetch`, `post`, `send(request(…))`, a keep-alive `Client`, redirects, gzip bodies) and server (`serve`, `serve_with`, a task a connection), sync and async; requests, responses, headers and chunked bodies parsed and written |
| `std.term` | [[Language/Standard-library/Term]] | The terminal: `is_tty`, `size`, raw mode (`raw_mode`, `restore`), styles and colours (`style().fg(c).bold().paint(s)`), cursor sequences, `strip` and `width`, keys (`parse_key`, `key_reader`), a line editor (`LineEdit`, `Editor`) |
| `std.signal` | [[Language/Standard-library/Signal]] | SIGINT and SIGTERM as events a task awaits: `listen()`, `Signals.next()`, `interrupted()` |
| `std.char` | [[Language/Standard-library/Char]] | Character classes, case and digits, as methods on `char` (ASCII) |
| `std.int` | [[Language/Standard-library/Int]] | Methods on every integer type: `gcd`, `pow`, Euclidean division, checked, wrapping, saturating and overflowing arithmetic, `mulmod`, `powmod`, `modinv` |
| `std.num` | [[Language/Standard-library/Num]] | Exact parsing and printing of integers and floats; integers in any radix and width, with `ParseIntError` |
| `std.bigint` | [[Language/Standard-library/Bigint]] | `BigInt`, integers of any size: arithmetic with Karatsuba and recursive division, `pow`, the three divisions, parsing and printing in any radix |
| `std.str` | [[Language/Standard-library/Str]] | Methods on `str`: search, split, trim, case, padding, replace |
| `std.text` | [[Language/Standard-library/Text]] | A `Scanner` for hand-written parsers, `ints` (every integer in a line), word wrap, aligned columns, `indent` and `dedent` |
| `std.fmt` | [[Language/Standard-library/Fmt]] | Format specs and the helpers of `Format` impls |
| `std.math` | [[Language/Standard-library/Math]] | Floating-point functions after fdlibm |
| `std.list` | [[Language/Standard-library/List]] | Methods on lists: building, `map` and the other higher-order operations, sorting, binary search, permutations and combinations |
| `std.iter` | [[Language/Standard-library/Iter]] | Lazy adapters and consumers over `Iterator<T>`, chained with `\|>`: `range`, `repeat`, `from_fn`; `map`, `filter`, `take`, `skip`, `zip`, `chain`, `flat_map`, …; `to_list`, `count`, `sum`, `fold`, `find`, `min`, `max`, … |
| `std.slice` | [[Language/Standard-library/Slice]] | The index arithmetic of slices |
| `std.option` | [[Language/Standard-library/Option]] | Methods on `Option` and `Result`: `map`, `and_then`, `unwrap_or`, `ok_or`, `map_err`, `expect`, … |
| `std.map` | [[Language/Standard-library/Map]] | Methods on maps (`get`, `get_or`, `update`, `values`, `items`, `merge`) and `counts` |
| `std.task` | [[Language/Standard-library/Task]] | Child tasks in numbers known at run time, cancellation, time limits, notifiers, channels, worker pools, the first of several |
| `std.time` | [[Language/Standard-library/Time]] | The monotonic and wall clocks, `Duration`, `Instant`, `DateTime` in UTC, RFC 3339 and ISO 8601 |
| `std.bench` | [[Language/Standard-library/Bench]] | Timing a closure over repeated runs: a warm-up that fixes the calls a run makes, `run`, `run_n`, `run_for`, the minimum, median and spread on one line, `black_box` |
| `std.log` | [[Language/Standard-library/Log]] | `error`, `warn`, `info`, `debug` to the standard error with a time, the level from `MYLA_LOG` |
| `std.test` | [[Language/Standard-library/Test]] | Expectations, temporary directories and the program under test, for test functions |
| `std.json` | [[Language/Standard-library/Json]] | JSON values, parsing, compact and indented writing, paths, typed getters; typed values by `#derive(Json)`, `encode` and `decode<T>` |
| `std.toml` | [[Language/Standard-library/Toml]] | TOML 1.0 documents, read and written back (`to_string`), with key and value positions; typed values by `#derive(Toml)`, `encode` and `decode<T>` |
| `std.csv` | [[Language/Standard-library/Csv]] | RFC 4180 CSV: records, a header row mapped to names, a stream read record by record, writing |
| `std.ini` | [[Language/Standard-library/Ini]] | INI files: sections, keys, comments, read and written in order |
| `std.yaml` | [[Language/Standard-library/Yaml]] | The safe subset of YAML 1.2: block and flow collections, quoted and block scalars, the core schema, writing; anchors, tags and second documents refused |
| `std.xml` | [[Language/Standard-library/Xml]] | Well-formed XML 1.0 without a DTD: a tree, a pull reader over a text or a stream, writing with escaping and indentation |
| `std.bytes` | [[Language/Standard-library/Bytes]] | Strings as `[uint8]` and back, checking and building UTF-8 |
| `std.encoding` | [[Language/Standard-library/Encoding]] | Hex and Base64 (standard and URL-safe), strict decoding |
| `std.url` | [[Language/Standard-library/Url]] | Percent-encoding, query strings, parsing and building URLs |
| `std.hash` | [[Language/Standard-library/Hash]] | The `Hasher` that `Hash` builds on, and wyhash |
| `std.checksum` | [[Language/Standard-library/Checksum]] | FNV-1a, CRC-32 and Adler-32, incremental |
| `std.regex` | [[Language/Standard-library/Regex]] | Regular expressions in linear time: RE2's syntax on bytes, `find`, `captures`, `replace`, `split` |
| `std.set` | [[Language/Standard-library/Set]] | `Set<T>` in insertion order: insert, remove, union, intersection, difference |
| `std.deque` | [[Language/Standard-library/Deque]] | `Deque<T>`, the double-ended queue and the queue: a ring buffer, indexable |
| `std.heap` | [[Language/Standard-library/Heap]] | Binary heaps: `Heap<T: Ord>`, least or greatest first, and `KeyedHeap<T>` by an `int64` priority |
| `std.cache` | [[Language/Standard-library/Cache]] | `Lru<K, V>`, a least-recently-used cache in constant time over a map and an index-linked list; `Memo<K, V>`, memoising a function or a recursion given as a step |
| `std.grid` | [[Language/Standard-library/Grid]] | `Grid<T>`, a 2D array of cells: read from text and printed, `at` and `set` with bounds, 4 and 8 neighbours, `(x, y)` positions |
| `std.graph` | [[Language/Standard-library/Graph]] | Searches over a neighbour function: BFS, DFS, Dijkstra, A*, topological sort, connected components, and dense forms over numbered nodes |
| `std.bitset` | [[Language/Standard-library/Bitset]] | `BitSet`, fixed or growable sets of small integers over `uint64` words: `popcount`, union, intersection, difference, complement |
| `std.unionfind` | [[Language/Standard-library/Unionfind]] | `UnionFind`, disjoint sets with path compression and union by rank |
| `std.btree` | [[Language/Standard-library/Btree]] | B+ trees: `SortedMap<K: Ord, V>` and `SortedSet<T: Ord>` in key order, `floor`, `ceiling`, `range`, `first`, `last` |
| `std.digest` | [[Language/Standard-library/Digest]] | MD5, SHA-1, SHA-2 and HMAC, one-shot and incremental, as bytes and as hex |
| `std.random` | [[Language/Standard-library/Random]] | `Rng`, a seeded generator (xoshiro256**): seeded or from the system's entropy, integers in a range without bias, floats, shuffles, choices |
| `std.uuid` | [[Language/Standard-library/Uuid]] | UUIDs of RFC 9562, version 4 (random) and 7 (a time), parsing and the canonical text |
| `std.compress` | [[Language/Standard-library/Compress]] | DEFLATE and the gzip and zlib formats: `inflate`, `gunzip`, `zlib_decompress` and `Read` streams over any stream; `deflate`, `gzip`, `zlib_compress` at levels 0 to 9 and `Write` streams |
| `std.archive` | [[Language/Standard-library/Archive]] | tar archives read and written (ustar, pax, GNU long names), zip archives read (stored, deflate), safe entry names |
| `std.args` | [[Language/Standard-library/Args]] | Command-line arguments: a declarative spec of flags, options, positionals and subcommands, parsing, the generated help |
| `std.rt` | [[Language/Standard-library/Rt]] | The runtime in Myla; not for programs |
