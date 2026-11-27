---
id: MYLA-818
title: "An interpreted case blocked in a system call passes its time limit"
type: bug
status: review
priority: low
labels: [interpreter, testing]
---
Found by [[MYLA-792]] (D259). `myla test --timeout` stops an interpreted case as it runs its blocks and as its tasks wait, but not while the interpreter is inside a blocking primitive of the case's own: a child process it waits for, a blocking read of a socket. Natively the runner kills the case's process (and its process group) at the limit.

```myla fragment
import std.process as process

#test
fun starts_a_sleeper() {
    let r = process.command("sh").arg("-c").arg("sleep 300").output()
}
```

`myla test --timeout 2 t.my` waits the 300 s and then passes; `myla test --native --timeout 2 t.my` reports `FAIL  starts_a_sleeper: timed out after 2 s` after 2 s and leaves no `sleep` behind.

- [x] The interpreter's blocking primitives that can wait without end (`__run_with`, `__reap`, a blocking read of a descriptor or a socket) wait at most until a running case's deadline (`Interp.case_deadline`), killing the child they started, and the case then times out
- [x] A case of `tests/burn/test_test_native.py`'s `_TIMEOUT` with a child process, on both runners

## What changed

In [[selfhost/interp.my]], only while a case runs with a time limit (`case_deadline` set; `myla run` and `--timeout 0` wait as before):

- `case_wait`: a host wait (`__poll`, `__poll_write`, `__sock_poll`) cut to what the limit leaves; a wait it cut short with nothing ready times the case out. It bounds `__poll`, `__poll_write`, `__sock_poll`, and `__wait_writable` and `__wait_socket` outside a task.
- `case_readable`: `__read` and `__read_bytes` wait for their descriptor through `case_wait` first.
- `case_write`: `__write` and `__write_bytes` (outside the captured stdout) write a piece of PIPE_BUF bytes at a time, each once the descriptor has room: a child that didn't read its input held the write past the limit too (found while testing this, same cause).
- `case_run`: `__run_with` and `__run` start the child with `__spawn_with` and `__spawn`, read its output and error as they come and wait for its end (its pidfd) through `case_wait`; past the limit the child is killed and reaped. Its status is the host reap's (`__run_exit_code`, `__run_signal`), its error output the interpreter's `run_stderr`, which `__run_stderr` gives. A child that couldn't be started is the host's own run, which fails as the spawn did.
- `case_reap`: `__reap` polls `__try_reap` between naps (1 ms doubling to 50 ms: a process ID gives nothing to poll) until the limit, then kills and reaps.
- The children a case starts (`__spawn`, `__spawn_with`, `__spawn_piped`) are noted (`case_children`, `note_child`) until reaped (`__reap`, `__try_reap`, `forget_child`); when the case ends, the ones left are killed and reaped (`end_children`), as natively its process group is (D272).
- Killing is `kill_tree`: on Linux the child and every descendant `/proc/<pid>/task/*/children` names, each stopped (SIGSTOP) as it is found and then all killed (SIGKILL): `sh -c "sleep 300"` forks its `sleep` here (dash), which killing `sh` alone left. Elsewhere (Windows) the child alone.

## Evidence

- Before (BASE 3add216): `timeout 10 build/myla test --timeout 2 t.my` of the case above was killed by `timeout` after 10 s (it would have waited the 300 s). After: `FAIL  starts_a_sleeper: timed out after 2 s` in 2.1 s, status 1, no `sleep 300` left (`pgrep`). Before the descendants were killed, the case timed out but left `sleep 300` behind.
- A case writing 1,000,000 bytes to the input of `sleep 299` (which never reads it): before, `timeout 15 … --timeout 2` killed after 15 s; after, `timed out after 2 s`.
- [[tests/burn/test_test_native.py]]'s `_TIMEOUT` has three new cases, `waits_for_a_child` (`output()` of `sh -c "sleep 316"`), `waits_for_its_child` (`spawn()` then `wait()` of `sh -c "sleep 315"`) and `writes_to_a_child` (200,000 bytes to `sleep 314`'s input), and `test_a_case_s_time_limit` checks after each runner that none of the sleeps is left. It passes on both runners (`1/7 passed.`, the same report).
- Suites (2026-11-18): `test_test_native`, `test_process`, `test_test_functions`, `test_test_names` 53 tests OK; `scripts/test.sh` 1,856 tests, one failure, the known timing test `test_children_run_in_parallel` (MYLA-745), which passes alone; the Windows suites (`test_windows`, `TestWindowsDebugInfo`) under Wine 69 OK with `TMPDIR` unset. `build/myla test lib/std/process.my` 53/53 interpreted and `--native`, `lib/std/net.my` 102/102, `lib/std/signal.my` 11/11. The playground's `play.wasm` runs a case that writes stderr and a file and reads it back as before (the waits are the WASI shim's polls). `scripts/bootstrap.sh` reaches its fixed point; `scripts/check-seed.sh` passes, on Windows under Wine too.

## Proposals

Accepted by the owner on 2026-11-19 as D303.

- **The children a case leaves are killed at every case's end**, not only past the limit: the interpreted equivalent of D272's "killed when the case ends", so a case that starts a child and passes doesn't leave it either. Alternatives: kill them only when the case timed out (closer to the task's words, but a passing case's leftover outlives `myla test` interpreted and not natively); leave them (as before).
- **Descendants by /proc, not a process group**: the interpreter can't put a child in a group of its own without a new option of the spawn primitives (setpgid between fork and exec, the Linux platform's), which wave 1 doesn't add (D207). A new `opts` letter for "a group of its own" would let the interpreter kill the group as natively; until then /proc covers Linux, and Windows kills the child alone (its job objects are [[MYLA-819]]'s Windows part).
