---
id: MYLA-399
title: "Drop Read.read_str and Write.write_str now that str and [uint8] convert in one copy?"
type: improvement
status: done
priority: low
labels: [stdlib, io, decision]
---
Found by the platform lane ([[MYLA-369]]). `std.io`'s traits have a method for each kind, `read`/`read_str` and `write`/`write_str` ([[MYLA-338]]), because a `str` became a `[uint8]` only byte by byte: 50 MB of lines took 331 ms through `[uint8]`, 75 ms through `str`. Since [[MYLA-369]] the two convert in one allocation and one copy (`__str_to_bytes`, `__bytes_to_str`), and the measurement turned round: natively, `Buffered` reading through `read` and `bytes.to_str` took 100 to 148 ms (median 106) where `read_str` took 129 to 153 ms (median 132) on the same machine; interpreted, on 2 MB, 6.6 s against 6.1 to 6.5 s ([[Language/Standard-library/Io#speed]]). Why the `[uint8]` path, with two more copies, is faster natively isn't known yet (the cells' size classes, perhaps): worth a look either way.

The owner decides:

- **A. Keep both** (as built): nothing changes for the nine modules with streams (`std.io`, `std.fs`, `std.process`, `std.net`, `std.http`, `std.compress`, `std.archive`, `std.xml`, the tests), and text keeps a method of its own.
- **B. Drop both from the traits** (recommended once the parallel lanes have merged): `Read` is `read` alone, `Write` `write` and `flush`; `Buffered` pulls bytes and keeps its text methods (`read_line`, `read_exact`, `read_to_end`), `BufferedWriter` gains an inherent `write_str`; a stream implements one method less. A `__read` that gives a `[uint8]` would spare the descriptor's conversion.
- **C. Keep `write_str` only**, as a convenience every writer has, and drop `read_str`.

- [x] The decision, in [[Project/Decisions]] (D177, B)
- [x] If B or C: the traits, their implementations, the pages and the tests changed, measured again

## What was built

- **The traits** ([[lib/std/io.my]]): `Read { read }`, `Write { write, flush }`. `Buffered` pulls bytes (`pull_bytes`, and `pull` converts each read to text once) and keeps `read_line`, `read_exact`, `read_to_end` and their async twins; its own `read` gives a big read straight from the stream. `BufferedWriter` has an inherent `write_str` (and its buffer goes on as bytes). `read_all` and `copy` read and write bytes.
- **Every stream:** `FdStream`, `MemoryStream` (std.io), `File` (std.fs), `ChildStdin`, `ChildStdout`, `ChildStderr` (std.process), `TcpStream` (std.net), `Decoder` and `Encoder` (std.compress), and the test streams of std.archive, std.csv, std.xml, std.compress and `test_compress`, `test_xml`. Callers: std.http's connection, std.csv's and std.xml's stream readers (each chunk converted once), std.process's `read_rest`, the burn tests (`test_net`, `test_archive`, `test_compress`, `test_xml`), the module tests. std.yaml doesn't stream.
- **Two primitives, staged** (D156): `__read_bytes(fd, n) -> [uint8]` and `__write_bytes(fd, b: [uint8])`, std.rt's `read_bytes` and `write_bytes` (in the interpreter through `__read` and `__write`), so the streams of a descriptor (`FdStream`, `File`, a child's pipes) read into a list and write from one without a `str` between. Without them a bulk copy converts every byte twice: four times slower (below). [[tests/burn/test_platform_primitives.py]]'s `Bytes.test_read_bytes_and_write_bytes` (interpreter = native, aarch64 and wasm32 too).
- **Pages:** [[Language/Standard-library/Io]] (the traits, `BufferedWriter.write_str`, a stream of one's own with `read` alone, the speed section), [[Language/Standard-library/Fs]], [[Language/Standard-library/Process]], [[Language/Standard-library/Net]], [[Language/Standard-library/Compress]] (examples and tables), [[Language/Standard-library]] and [[Language/Targets]] (the primitives), [[Architecture/Interpreter]]; the myla skill (both copies).

## A choice made (the owner decides)

- **`TcpStream`'s async text twins went too**: `read_str_async` and `write_str_async` were inherent methods, not the traits', but they were the text twins of `read_async`/`write_async`, which mirror the traits; keeping them would leave a stream with `read_str_async` and no `read_str`. Alternative: keep them as a convenience for line protocols over a socket (`test_net`'s echo programs got `bytes.from_str`/`to_str` instead). `UdpSocket`'s `send_str_to`/`recv_str_from` stay: a socket of datagrams isn't a `Read` or `Write`.
- Sockets still convert: `__sock_recv`/`__sock_send` deal in `str`, so a `TcpStream` converts each read and write once (network-bound; a `[uint8]` twin of them would be the same staging again). Filed as nothing yet: worth it only if a measurement shows it.

## Evidence

Built on `9681bb3`.

- **Before:** a stream with `read` alone ([[lib/std/io.my]]'s `bytes_only_streams` case, and the same as a program) fails to check with the tools at the base: `type error: impl of trait 'io.Read' for 'Countdown' is missing method(s): read_str`; after, it prints `9876` and `5`. With the traits changed and the old impls in place, `myla test lib/std/io.my` fails with `impl of trait 'Read' for 'fs.File' declares method(s) not in the trait: read_str` (and `write_str`), which is what led through the nine modules.
- **Module cases** (`build/myla test lib/std/<m>.my --stdlib lib`): io 24/24, fs 73/73, process 34/34, net 93/93, http 156/156, compress 136/136, archive 83/83, csv 38/38, xml 89/89 interpreted; io, fs and process natively too (`--native`, 24, 73, 34). Burn: `test_net` (13, 1 skipped), `test_compress`, `test_xml`, `test_archive` OK; `test_platform_primitives` OK, and on `aarch64-linux` (qemu) and `wasm32-wasi` (Node) through `scripts/test-target.py`.
- **Bootstrap:** byte-identical fixed point after each step (19,345,619 bytes with the traits changed, 19,367,143 with the primitives, 19,366,614 with the streams on them); the `Stage:` commit's seeds from `scripts/update-seed.sh`.
- **Measured** (natively on x86-64, 2026-11-09, medians of eleven runs interleaved; before: the base, through `read_str`/`write_str`; converted: the traits changed, the descriptors' bytes converted from and to `str`; now: on `__read_bytes`/`__write_bytes`):

  | What | Before | Converted | Now |
  | --- | --- | --- | --- |
  | `stdin().read_line()` over 50 MB of lines (0 to 120 bytes) | 130 to 139 ms | 119 to 121 ms | 131 to 133 ms |
  | 1 000 000 `write_str` of 48 bytes into a `BufferedWriter` over `fd_stream(1)`, to `/dev/null` | 14 ms | 15 ms | 14 ms |
  | `copy(fd_stream(0), fd_stream(1))` of the 50 MB | 7 ms | 10 ms | 7 ms |
  | `read_line` through a `Buffered<MemoryStream>` of the 50 MB (the file read too) | 268 ms | 279 ms | 288 ms |
  | 4 GiB `/dev/zero` to `/dev/null`, two `File`s, reads of 1 MiB (five runs) | 109 ms (`read_str`); 471 ms (`read`) | 481 ms | 111 ms |
  | 256 MiB of `head -c` through a `ChildStdout`, 64 KiB reads (five runs) | 126 ms (`read_str`); 128 ms (`read`) | | 130 ms |

  Interpreted, 2 MB of lines: 6.80 to 6.93 s before, 6.76 to 6.98 s converted, 6.67 to 6.80 s now (three runs each). The converted lines are faster than either, with two copies more, as [[MYLA-369]] saw; not the size classes (the reads' cells are in the same 8 KiB class either way). Not explained; the bulk copy decides for the primitives. The memory stream's lines are 7 % slower (a `Result` of a list more per read).
- **Suites** (tools from a bootstrap, `selfhost/embedded_std.my` restored for the commits): `scripts/test.sh fast` after the streams' last commit: 771 tests, 2 failures, both the embedded library behind `lib/` until the integrator's seed (`test_embedded_std`, `test_installed`'s language-server text). `python3 -m unittest` of `test_compiler_parity test_selfhost_cases test_error_corpus test_selfhost_checker test_lsp test_std_modules test_fs test_process test_stdin test_http test_net test_compress test_xml test_archive test_platform_primitives test_doc_blocks` (at the lane's end): 799 tests OK (4 skipped). `scripts/test-target.py wasm32-wasi test_std_modules`: OK.

## Comments

- 2026-11-09: the owner took the recommendation, B: D177.

## Review 2026-11-10

Signed off in [[Project/Review-2026-11-10]], with a follow-up in [[MYLA-420]]: a short read keeps a cell as large as the request (S1); interpreted bulk I/O is [[MYLA-414]]'s (S2); the socket line reader is [[MYLA-419]]'s (D180).
