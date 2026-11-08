---
id: MYLA-378
title: "Platform primitives for wave 3's gaps: a path's stat, a child's stdout and stderr, a descriptor as stdin"
type: feature
status: backlog
priority: low
labels: [platforms, primitives, stdlib]
---
Found by the file and process lanes ([[MYLA-339]], [[MYLA-340]]). Each is a primitive on x86-64, aarch64 and wasm32 and in the interpreter, and a seed staging (D156).

- [ ] `__stat(path) -> [size, mode, mtime_ns]`, so `fs.metadata(path)` doesn't open the file (today a file the program can't read is `PermissionDenied`, and a device, FIFO or socket gets size 0 and time 0). With `lstat`'s form, [[MYLA-363]]
- [ ] Spawning with stdout and stderr inherited or null, not only piped: then `Command.stdout_from` and `stderr_from`, and a child that writes more than 64 KiB to a stream nobody reads no longer stops
- [ ] A descriptor as a child's stdin, so a `Pipeline` joins its two children directly instead of the parent copying (which a consumer that writes much more than it reads can still stall)
- [ ] `__close` records its errno, so `File.close()` reports EIO and doesn't need an `__fstat` first
