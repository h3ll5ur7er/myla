---
id: MYLA-340
title: Streaming processes
type: feature
status: review
priority: medium
labels: [stdlib, process, streams, wave-3]
---
Wave 3 of [[Project/Standard-library-roadmap]], roadmap #46. Today `run` and `Command.output` capture a child's whole output.

- **Owns:** `lib/std/process.my`, `docs/Language/Standard-library/Process.md`
- **Needs:** [[MYLA-336]], [[MYLA-338]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [x] `Command.spawn() -> Result<Child, SpawnError>` with the child's stdin a `Write` and its stdout and stderr `Read`s
- [x] `wait`, `kill`, `try_wait`; async forms
- [x] A pipeline of two children joined by a pipe
- [x] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [x] Its page below [[Language/Standard-library]], with a doc block that runs

## Done (2026-11-08)

`Command.spawn() -> Result<Child, SpawnError>` over [[MYLA-336]]'s primitives, in [[lib/std/process.my]]; the page is [[Language/Standard-library/Process#children-as-streams]].

- **Streams:** `ChildStdin` (`Write`, `close`), `ChildStdout` and `ChildStderr` (`Read`, `Pollable`, `close`), `std.io`'s traits (no import cycle: `std.process` → `std.io` → `std.fs`). A stream used after `close`, or closed twice, is `IoError.Other(9)` (EBADF).
- **Holding the streams:** the `Child` holds each until `take_stdin()`, `take_stdout()` or `take_stderr()` gives it out once, as Rust's `Option::take` on its public fields does. Values have no destructor, so the `Child` must know which descriptors are still its own to close: a stream read from a field would be a second holder. `wait` closes the held input first (so `cat` ends) and reads the held output and error to their end, dropping them (so a child writing much to a stream nobody took doesn't stop), then reaps.
- **Waits:** `wait`, `wait_with_output`, `try_wait`, `kill` (SIGKILL; `Ok` without a signal once reaped, the pid may be reused), `id`; `wait_async` and `wait_with_output_async` wait on the pidfd and the pipes with the task suspended (`__wait_readable`, `__wait_either`), and a cancelled task gets `IoError.Cancelled` with the child left running. The blocking wait polls the pidfd and reaps with `__try_reap`, so a second reap through a copy is `Other(10)` (ECHILD) rather than a made-up status.
- **Input:** `stdin_from(Stdio.Piped | Inherit | Null)` beside the existing `stdin(text)` (the name `stdin` was taken). `spawn` pipes by default; `output` inherits as before, and takes `Null` (and `Piped`, which it has nobody to write) as an empty input. **Output and error are always pipes:** the primitives take no descriptor, so they can't be inherited or null; there is no `stdout_from`/`stderr_from`.
- **Pipeline:** `a.pipe(b).output() -> Result<PipelineOutput, SpawnError>` (`first`, `second`: `Output`s). The parent copies (no primitive takes a descriptor for the input): 64 KiB reads of the first's output, written to the second in 16 KiB pieces with the second's output and both errors read between pieces. A second child that ends early gives the first SIGPIPE, as a shell does. A second that writes more than four times what it reads could still stall the copy; a primitive that takes the input's descriptor would end that.
- `ExitStatus` and `SpawnError` gained `#derive(Eq)`; `SpawnError` gained `message()` and `Format` (D168).

## Evidence

- Test first: the test functions, run against the module as it was at 1dd86a6, fail to check (23 errors: `type 'Command' has no method 'spawn'`, `unknown type 'ChildStdin'`, …).
- `build/myla test lib/std/process.my --stdlib lib`: 24/24 interpreted, `--native` 24/24, `--target aarch64-linux` (qemu) 24/24, `--target wasm32-wasi` (Node) 24/24, where each test function sees `Unsupported` at its first spawn and stops (a wasm32 program built from `spawn`, `stdin_from(Null)` and a pipeline prints `no processes on this target` for each). 11 test functions: a round trip through `cat`, closed streams, lines in and out one at a time through a `Buffered`, `try_wait`/`kill`/`Signaled(9)`, `wait` draining 300 KB of output and of error nobody took, `wait_with_output` with a text input, the three input modes in `spawn` and `output`, the spawn errors, a pipeline of 16 MiB (`head | wc -c`) and of 512 KiB collected out of the second (`head | tr`), one cut short (`head -c 50000000 | head -c 5`: `Signaled(13)`), and the async waits.
- `python3 -m unittest tests.burn.test_process tests.burn.test_time tests.burn.test_std_modules tests.burn.test_doc_blocks`: 28 tests, OK. `scripts/bootstrap.sh`: byte-identical fixed point (13,970,803 bytes).
- Natively, best of five: 256 MiB from `head -c 268435456 /dev/zero` through a `ChildStdout`, 64 KiB a `read_str`: 118 ms, 2,160 MB/s (a shell's `head | cat > /dev/null`: 105 ms); `read` (`[uint8]`): 469 MB/s. 256 MiB through `head | wc -c` as a pipeline: 250 ms (1 GB/s; 380 ms on a busier run).
