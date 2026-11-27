---
id: MYLA-946
title: "Measure what a socket's write time limit does on Windows: test_windows' client reads every byte after the 30 s close"
type: chore
status: todo
priority: medium
labels: [net, windows, testing]
---
[[MYLA-926]] step 2 (group E, 2026-11-24) changed `test_windows`' socket case to expect `sent true, all read true` on Windows, `all read false` elsewhere: on the native runner the client read every byte even though the program's 30 s limit closed the handle while the send was going on, where under Wine `closesocket` cancels the pending overlapped send. The reason given (Winsock delivers a queued TCP send at a graceful close, or the send ended within the 30 s) was reasoned, not measured; the owner asked for it to be measured (2026-11-24) rather than taken.

- [ ] On `windows-latest`: when the send ends against when the limit closes the socket, and what the peer reads after the close (a probe in the test's log, or `scripts/windows-runner.py`'s rates)
- [ ] If a write limit doesn't stop a send on Windows, fix std.net/std.platform so the limit means the same there (the send cancelled, the peer's read ending short), and the test's expectation the same on every machine; if it does and only the bytes already queued arrive, say so in the test and [[Language/Standard-library/Net]]
