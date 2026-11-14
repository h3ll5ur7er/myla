---
id: MYLA-716
title: "The platform interface in Myla's terms: what MYLA-701 left"
type: improvement
status: backlog
priority: medium
labels: [platforms, windows, runtime, stdlib]
---
[[MYLA-701]] (D208) made `std.platform`'s errors cause codes, a directory's entries names and kinds, a file its kind, size and permissions, and processes and sockets capabilities a target declares; `tests/burn/test_platform_interface.py` holds the modules to one interface. Left, none needed before Windows' steps ([[MYLA-702]] on), each where a step will meet it:

- [ ] **The poller in Myla's terms.** `poller_watch`, `poller_watch_socket` (`again`: armed once more, EPOLLONESHOT's shape), `poller_event(i)` and `poller_event_ready(i)` over a buffer of the last wait are epoll's form; wasm32 builds it on `poll_oneoff` (a legitimate implementation, not a translation: it stays), Windows will on IOCP ([[MYLA-706]]). A `POLLER` capability, and a wait that gives `(token, ready)` pairs, would let a target without one (and the interpreter) say so. `park` and `unpark_one` are futex's (`addr`, `seen`): wasm32's do nothing, as one worker needs; Windows' are `WaitOnAddress`/`WakeByAddressSingle`, the same shape, so they can stay.
- [ ] **`Other`'s numbers on Windows.** std gives the causes an error type has no variant for Linux's numbers on every target (`code_number`: `Other(9)` a closed handle, `terminal error 22`, `SpawnError.WorkingDir(2)`), and wasm32 its unmapped errnos Linux's too ([[MYLA-426]]). A Windows code with no cause is `Other` of its own number (D129). Decide whether wasm32 keeps Linux's numbers or gives WASI's own (then `test_fs.py`'s `ERRNOS` changes there), and whether std's own (`Other(9)`, `Other(11)`, `Other(27)`, `Other(29)`) become causes of their own (`Closed`, `WouldBlock`, …), a change programs see.
- [ ] **Texts of a failed write.** `std.rt`'s and `std.io`'s `errno_text` name ENOSPC, EIO, EFBIG and EDQUOT by Linux's numbers; a platform's `error_text(code)` would name its own (`ERROR_DISK_FULL`).
- [ ] **`SpawnError.WorkingDir(int32)`** holds Linux's number of why (D189). Proposal: `WorkingDir(IoError)`, which needs `IoError` to be `Eq` (`SpawnError` derives it).
- [ ] **std.http's `accept_fate`** keys EMFILE and ENFILE (`Other(24)`, `Other(23)`): Windows' `WSAEMFILE` needs a cause (`TooManyOpen`?) or its own number there.
- [ ] **`from_errno`** stays for programs that hold a Linux errno; nothing in std calls it. Remove it, or keep it documented as Linux's.
- [ ] **One Linux layer** ([[MYLA-265]]'s second box): `platform.my` and `platform_aarch64.my` still differ only in system-call numbers, `struct stat`'s mode offset and a few `*at` calls; the changes of MYLA-701 were made twice.
