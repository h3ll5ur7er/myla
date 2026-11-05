---
id: MYLA-265
title: "The platform interface in Myla's terms, and one Linux layer"
type: improvement
status: backlog
priority: high
labels: [platforms, runtime, stdlib, design]
---
Found by [[Project/Reflection-2026-11]].

**The interface speaks Linux.** `std.platform` was the right seam: the aarch64 port was mostly system-call numbers. But its interface is Linux's:
- negative Linux errnos;
- `getdents64` records;
- `st_mode` bits;
- fork/exec;
- epoll and eventfd;
- futex.

So wasm had to translate WASI into Linux shapes:
- directory records are rewritten as `getdents64`'s;
- mode bits are invented from file types;
- WASI's errnos are mapped onto Linux numbers, and anything unmapped becomes EIO;
- `getcwd` comes from `PWD`;
- the poller emulates epoll on `poll_oneoff`;
- `park` does nothing.

macOS and Windows would do the same again.

**Two near-copies.** `platform.my` and `platform_aarch64.my` differ in 136 diff lines, and x86-64 has the same `*at`, `pipe2`, `dup3`, `ppoll` and `epoll_pwait` calls aarch64 uses. Nothing checks that the three platform modules offer the same functions.

- [ ] The interface in Myla's concepts:
  - a file's kind and size;
  - a directory's entries as names and kinds;
  - an error as a cause ([[MYLA-190]], D113), with an "unsupported on this target" cause;
  - processes, the poller, parking and the clock as operations a target may lack.

  `std.rt` and std above it adapted.
- [ ] One Linux layer with each architecture's system-call numbers in a table
- [ ] A test that every platform module offers the same functions with the same types
- [ ] Choosing the module per target through [[MYLA-245]]'s code per target, replacing the loader's text substitution (`for_target`)
