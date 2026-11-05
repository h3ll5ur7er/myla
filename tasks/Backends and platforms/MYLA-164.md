---
id: MYLA-164
title: "Target: macOS"
type: feature
status: backlog
priority: low
labels: [backend, platforms]
---
A target of [[MYLA-62]] after [[MYLA-162]] and the aarch64 backend ([[MYLA-163]]; Intel Macs need the x86-64 one). macOS has no stable system call ABI: the platform layer links libSystem (D117 (2)), and Apple Silicon runs only signed binaries ([[MYLA-160]] settles linking and signing).

- [ ] The platform layer over libSystem (memory, files, processes, threads and parking, thread-local state), on arm64 and x86-64
- [ ] Linking and signing what's needed to run a binary; the parity, stress and concurrency programs pass on a macOS runner

## What the first two targets say about this one (2026-11-04, [[Project/Reflection-2026-11]])

The aarch64 backend ([[MYLA-163]]) is the code generator for Apple Silicon. What differs on macOS is everything the Linux targets take for granted:
- **Objects and symbols:** Mach-O through clang's assembler and linker (D125 already uses clang for wasm), with `_` before every symbol, other section names and no `.note.GNU-stack`. The GAS/ELF text `assemble_source` writes today assumes ELF throughout, so [[MYLA-269]] (an object model) comes first, or at least the target description's symbol prefix and sections ([[MYLA-262]]).
- **The calling convention:** Apple's variant of AAPCS64 (x18 reserved, which the backend doesn't use; other rules for variadic and small stack arguments, which matter only at C boundaries, [[MYLA-272]]).
- **Thread-local state:** the Linux runtime sets `tpidr_el0` through `clone`'s `CLONE_SETTLS`; on macOS threads come from `pthread_create` and the worker's state needs the system's thread-local storage instead.
- **The poller:** kqueue (with `EVFILT_PROC` for child processes) in place of epoll and the eventfd (D124); the platform interface in Myla's terms ([[MYLA-265]]) keeps this out of `std.rt`.
- **Stack overflow:** a guard page and `sigaltstack` as on Linux, but through libSystem's signals and Mach exceptions.
- **Errors:** macOS's errno numbers differ from Linux's (EAGAIN 35, ENOSYS 78), and `unlink` on a directory gives EPERM, which `std.fs.remove_dir_all` must not take for EISDIR; [[MYLA-266]] and [[MYLA-190]] decide how programs see errors.

- [ ] [[MYLA-262]], [[MYLA-265]] and [[MYLA-269]] (or their parts this target needs) before the port
