# Standard library

Myla has built-in functions known to the checker, and a small standard library written in Myla under [[lib/std/io.my|lib/std/]]. Both work without libc: natively they rest on the platform layer `std.platform`, raw Linux system calls on x86-64 and aarch64 and WASI's imports on wasm32 ([[Architecture/Native-backend]]), and so does the interpreter, which is a native program itself. What a target lacks shows as an error of its own, `Unsupported` (D129, D132): on wasm32 `run`, `run_async` and `command(…).run()` fail with `SpawnError.Unsupported`, as there are no processes. What each target can do (processes, suspending input, the file system it sees, the working directory) is on [[Language/Targets]].

[TOC]

## Built-in functions

These names are reserved: no declaration may reuse them. The ones on a receiver are methods only ([[MYLA-221]]).

| Function | Signature | Notes |
| --- | --- | --- |
| `print(x)` | one integer, float, `char`, `bool` or `str`, or a value whose type implements `Format` (D159) | Writes the value and a newline to stdout |
| `x.len()` | list, map, `str` or `StringBuilder` → `int` | A method; strings and builders: bytes |
| `xs.push(v)`, `xs.pop()` | list | Methods; need a `var` place |
| `m.contains(k)`, `m.keys()`, `m.remove(k)` | map | Methods; `remove` needs a `var` place |
| `get(m, k)` | map → `Option<V>` | The one entry here that is a prelude function, not a built-in: an ordinary generic function every program sees (a declaration of another `get` is a duplicate), so its errors read like any call's |
| `s.chars()` | `str` → `[char]` | A method |
| `format(fmt, args…)` | → `str` | `fmt` is a literal; see [[Language/Collections-and-strings]] |
| `StringBuilder()`, `sb.append(s)`, `sb.append(s, start, end)`, `sb.append_byte(b)`, `sb.build()` | | Methods but `StringBuilder()`; `append(s, start, end)` adds the bytes `s[start..end]` ([[Language/Collections-and-strings]]) |
| `assert(cond[, msg])`, `panic(msg)`, `unreachable()` | | See [[Language/Attributes-and-testing]] |

The low-level primitives `__write`, `__read`, `__poll`, `__exit`, `__args`, `__read_file`, `__write_file`, `__list_dir`, `__mkdir`, `__stat`, `__getcwd`, `__getenv`, `__sqrt`, `__f64_bits`, `__f64_from_bits`, `__unlink`, `__rmdir`, `__rename`, `__io_errno`, `__run`, `__run_stderr`, `__run_exit_code`, `__run_signal`, `__run_errno` and `__task_cancelled`, and the primitives behind `std.time`, `std.task`'s timers and `std.process`'s child processes (`__clock_ns`, `__sleep`, `__spawn`, …) exist for the standard library; call the `std` functions instead. A call of one from a program outside the standard library compiles, with the warning `primitive` (D100, [[MYLA-186]]): it is for code that knows what it does, such as a new std function in the making, which says so with `#allow(primitive)` or `#allow(primitive(__poll))` (D161, [[Language/Attributes-and-testing#warnings-and-allow]]).

## Modules

One page per module (D164). A new module adds its row here.

The conventions (D164): operations on built-in types are methods (`s.split(",")`, `xs.sorted()`), and `std.str`, `std.char`, `std.int`, `std.list`, `std.option` and `std.map` are seen by every program without an import ([[MYLA-320]]); everything else is a function of its module (`path.join(a, b)`). Strings are bytes and character classes ASCII. A function that can fail returns a `Result` with its module's error enum.

| Module | Page | Holds |
| --- | --- | --- |
| `std.io` | [[Language/Standard-library/Io]] | Writing to a descriptor, the buffered `Reader`, async reads |
| `std.fs` | [[Language/Standard-library/Fs]] | Whole-file reads and writes, directories, `IoError` |
| `std.process` | [[Language/Standard-library/Process]] | Arguments, the environment, exit, running programs (`run`, `command`) |
| `std.char` | [[Language/Standard-library/Char]] | Character classes, case and digits, as methods on `char` (ASCII) |
| `std.int` | [[Language/Standard-library/Int]] | Methods on every integer type: `gcd`, `pow`, Euclidean division, checked, wrapping, saturating and overflowing arithmetic, `mulmod`, `powmod`, `modinv` |
| `std.num` | [[Language/Standard-library/Num]] | Exact parsing and printing of integers and floats |
| `std.str` | [[Language/Standard-library/Str]] | Methods on `str`: search, split, trim, case, padding, replace |
| `std.fmt` | [[Language/Standard-library/Fmt]] | Format specs and the helpers of `Format` impls |
| `std.math` | [[Language/Standard-library/Math]] | Floating-point functions after fdlibm |
| `std.list` | [[Language/Standard-library/List]] | Methods on lists: building, `map` and the other higher-order operations, sorting, binary search, permutations and combinations |
| `std.slice` | [[Language/Standard-library/Slice]] | The index arithmetic of slices |
| `std.option` | [[Language/Standard-library/Option]] | Methods on `Option` and `Result`: `map`, `and_then`, `unwrap_or`, `ok_or`, `map_err`, `expect`, … |
| `std.map` | [[Language/Standard-library/Map]] | Methods on maps (`get_or`, `update`, `values`, `items`, `merge`) and `counts` |
| `std.task` | [[Language/Standard-library/Task]] | Child tasks in numbers known at run time, cancellation |
| `std.time` | [[Language/Standard-library/Time]] | The monotonic clock |
| `std.test` | [[Language/Standard-library/Test]] | Expectations, temporary directories and the program under test, for test functions |
| `std.json` | [[Language/Standard-library/Json]] | JSON values, parsing and writing |
| `std.toml` | [[Language/Standard-library/Toml]] | The TOML subset of manifests and lock files |
| `std.rt` | [[Language/Standard-library/Rt]] | The runtime in Myla; not for programs |
