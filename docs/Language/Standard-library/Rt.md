# std.rt

Not for programs: the runtime written in Myla ([[MYLA-162]], D117), which a native build loads with every program and compiles where the code generator calls it in place of the assembly routine it replaced. A standard library root without `std/rt.my` gets the copy the tools carry. Its parts, by what they are behind ([[Architecture/Native-backend#runtime-helpers]] lists the entries the generated code calls):

| Behind | std.rt's functions |
| --- | --- |
| `+`, `==` and `<` on strings, `chars()` and `for c in s`, integers as text in `format` | `str_concat`, `str_eq`, `str_cmp` (MYLA-318), `str_chars`, `str_char_at` (MYLA-318), `int_to_str`, `uint_to_str`, `float_to_str` (D155) |
| `m[k]`, `contains`, `keys()`, a builder's `append` | `map_lookup`, `map_keys`, `sb_append` |
| `print` and `std.io.write` | `print_str`, `print_int`, …, `write`: a line and its newline in one `writev`, so the lines of tasks on other workers don't interleave; a write error is D153's |
| `std.fs` | `read_file`, `write_file`, `list_dir`, `stat`, `mkdir`, `unlink`, `rmdir`, `rename`, `getcwd` (a path with a NUL byte is EINVAL, D153) |
| `std.io`'s reader, `std.process.args` and `env` | `read`, `poll`, `args`, `getenv` |
| `std.test` | `test_dir` and `test_program`: the running case's scratch root and the program under test, "" outside `myla test` (natively, the environment variables `MYLA_TEST_DIR` and `MYLA_TEST_PROGRAM` the harness of `myla test --native` sets) |
| `std.process.run` and `Command` | `run`, `run_with`, `spawn`, `spawn_with`, `reap`, `kill`, `close` (fork, exec, both outputs read as they come through poll, wait) |
| the heap | `alloc`, `free` and their tasks' forms (D157) |
| tasks, timers, the reactor | the executor, `cancel_after`, the timers and the descriptor watches ([[Language/Concurrency]]) |

It works on raw memory through primitives only the standard library may call (D152): `__load8`, `__load32`, `__load64`, `__store8`, `__store32`, `__store64`; a list's cell and back (`__list_addr`, `__list_of`, the list type from the context); `__alloc`, `__free`, `__addr_of`, `__str_of`; the bulk `__copy_bytes` and `__equal_bytes`, which each backend does natively; the atomics `__cas64`, `__xchg64` and `__fetch_add64`, full barriers, and `__load_acq64` and `__store_rel64`, a load with acquire and a store with release ordering (`ldar` and `stlr` on aarch64, plain moves on x86-64, whose ordering gives both, MYLA-267). It makes system calls through `__syscall(n, a, b, c)`, records the errno `std.io` reports with `__set_io_errno`, reads the arguments and the environment through `__argv()` and `__environ()`, and leaves a run's stderr and status with `__set_run_stderr` and `__set_run_status`; addresses are `int64`.

Under it, `std.platform` is the platform layer, one module per target ([[lib/std/platform.my]] for x86-64 Linux, [[lib/std/platform_aarch64.my]], [[lib/std/platform_wasm.my]]; the loader takes the target's for `std/platform.my`): every system call std.rt makes, the numbers, flags and record layouts with them, and the process runner (fork, exec, poll, wait), behind functions that give a result or a negative errno (`open_read`, `read`, `write_line`, `mode_of`, `dir_read`, `run`, `cpus_allowed`, `park`, `unpark_one`, `exit`, …). A port to another system gives that module again; std.rt stays as it is. Its interface is Linux's (negative errnos, `getdents64` records, `st_mode` bits), which wasm32's module imitates; [[MYLA-265]] is to make it Myla's.
