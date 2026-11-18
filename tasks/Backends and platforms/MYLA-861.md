---
id: MYLA-861
title: "Windows: a program of many workers commits 16 MiB of heap for each worker that allocates"
type: bug
status: todo
priority: medium
labels: [platforms, windows, memory]
---
Found by [[MYLA-798]] (H12). Windows counts committed memory against the system's limit (RAM and page file), where Linux overcommits: std.platform's `map_memory` ([[lib/std/platform_windows.my]]) reserves and commits at once (`VirtualAlloc` with MEM_COMMIT | MEM_RESERVE), and std.rt's heap ([[lib/std/rt.my]], `alloc_mapped`, `map_aligned`) maps a 16 MiB chunk for each worker's arena the first time that worker allocates, with tasks 32 MiB of it for a moment (`map_aligned` maps a chunk more and gives the ends back). MYLA-798 made the workers' rings of ready frames (8 MiB each) committed as they are touched; the arenas are what is left.

Measured under Wine 9.0 (2026-11-17, MYLA-798's branch): `test_windows.HELPER sleep 3000` with `MYLA_THREADS=16`, a program that does nothing but sleep in one task, had between 4 and 11 mappings `rw-p` of exactly 16 MiB in `/proc/<pid>/maps` across two runs, so 64 to 176 MiB of heap committed. On a 4-CPU runner with 16 GB, 200 such children at once (`process/many-children`) would be some tens of GB.

To reproduce: build `HELPER` for `x86_64-windows`, run it under Wine with `MYLA_THREADS=16` and the arguments `sleep 3000`, and count the 16 MiB `rw-p` mappings of its process. CI's `windows` job (`process/a-child-s-commit`, MYLA-798's rates step) gives the same child's peak commit charge on Windows itself.

- [ ] Find why workers that run nothing of the program allocate (the executor's own lists?), and stop it where it isn't needed
- [ ] Commit an arena as the bump pointer reaches it (a platform function that commits a range, called by std.rt's allocator past the committed end) rather than at the map: the kernel never faults a reserved page in for a system call that writes into it (`ReadFile` into a fresh buffer fails with ERROR_NOACCESS), so committing on an access violation (what the rings do) doesn't do for the heap
- [ ] A measurement on CI's runner before and after (`process/a-child-s-commit`'s line in the rates step)
