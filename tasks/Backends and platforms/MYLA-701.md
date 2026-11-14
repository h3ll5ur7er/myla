---
id: MYLA-701
title: "Windows step 2: the platform interface in Myla's terms"
type: feature
status: todo
priority: high
labels: [platforms, windows]
---
A step of [[MYLA-165]], the Windows target, in the plan the owner accepted on 2026-11-14 ([[Project/Follow-up-plan#windows-2026-11-14]]). D208, the part of [[MYLA-265]] the port needs before it starts: Windows would otherwise translate its API into Linux shapes, as wasm32 does today.

- [ ] Errors as Myla's causes (D129) from the platform functions, not negative Linux errnos
- [ ] A directory's entries as names and kinds, not `getdents64` records
- [ ] A file's kind and size, not `st_mode` bits
- [ ] The poller and processes as operations a target may lack (`Unsupported`, D129)
- [ ] std.rt, std.fs, std.process, std.io, std.net and the interpreter's primitives adapted; wasm32's translation layer removed where the new shapes make it needless
- [ ] A test that every platform module offers the same functions with the same types
