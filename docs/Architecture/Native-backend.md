# Native backend

[[src/myla/compiler/codegen_x86.py]] turns the monomorphized program ([[Architecture/Monomorphization]]) into GAS/AT&T assembly for x86-64 Linux. [[src/myla/compiler/__init__.py]] writes `<out>.s`, runs `as --64` and `ld`, and deletes the intermediate files (`--keep-asm` keeps the `.s`). There is no libc: the runtime is emitted as assembly and talks to the kernel with system calls (D2, D29).

The self-hosted code generator ([[Architecture/Self-hosted-compiler]]) is a port of this one and uses the same conventions and layouts.

[TOC]

## Strategy

- One pass per function, no IR, no register allocation. Every expression leaves its result in `%rax`; binary operators evaluate the right operand, push it, evaluate the left, pop the right into `%rcx` (which is why native evaluation order is right to left: [[MYLA-8]]).
- Before emitting a function, `_layout_frame` walks its body and gives **every** local, temporary, match binding, loop counter and scratch value its own `%rbp`-relative slot, keyed by node id. Slots are never reused; the frame is rounded up to 16 bytes.
- Runtime helpers are emitted only when used (flags such as `_uses_float`, `_uses_run`).

## Calling convention

Internal and stack-based (never called from C):

- Arguments are pushed last-to-first, so argument *i* is at `16 + 8*i(%rbp)`; the caller pops them.
- Scalars (integers, floats as their f64 bit pattern, `char`, `bool`, `str` pointers, list/map/builder pointers) are passed by value in one 8-byte slot.
- Aggregates (structs, tuples, enums, function values) are passed as a **pointer** to the caller's storage. This is safe because parameters are immutable; a `var self` receiver is passed the same way, so writes reach the caller.
- An aggregate result uses a hidden first argument (sret): a pointer to storage the caller reserved, returned again in `%rax`.
- Function values are called as `code_ptr(env_ptr, args…)`; plain functions used as values get a `myla_<fn>__fnval` adapter that drops the env argument.

`_start` stores `argc`, `argv` and `envp`, calls `myla_<entry>`, then exits 0. All user functions are labelled `myla_<name>`.

## Value layout

| Type | Representation |
| --- | --- |
| integers, `char`, `bool` | One 8-byte slot holding the **canonical 64-bit value**: signed types sign-extended, unsigned zero-extended. After arithmetic `_wrap` re-canonicalises (`shl`/`sar`, `movl`, or `and`) |
| floats | The IEEE double bit pattern in a general register; arithmetic in `%xmm0`/`%xmm1`; `float32` is rounded with `cvtsd2ss`/`cvtss2sd` after each operation |
| `str` | Pointer to `[len:8][bytes…]`. Literals live in `.rodata`; strings built at run time are heap cells that are **never freed** ([[MYLA-18]]) |
| struct | Fields inline, each in its stored size, in declaration order |
| tuple | Elements inline |
| enum | `[tag:8][payload union]`: the tag is the variant's index; the payload area is as large as the largest variant |
| boxed (recursive) enum, as a member | An 8-byte pointer to a heap cell holding the inline enum value |
| function value | 16 bytes: `(code_ptr, env_ptr)`; `env_ptr` is 0 when nothing is captured |
| list `[T]` | Pointer to a heap cell `[len:8][cap:8][elem…]`, stride = the element's stored size |
| map `[K: V]` | Pointer to `[len:8][cap:8][slot…]`, slot = `[state:8][key:8][value]`, state 0 empty / 1 occupied; open addressing with linear probing, FNV-1a hash of the key bytes (string contents for `str`), capacity a power of two kept under 0.75 load |
| `StringBuilder` | Pointer to `[len:8][cap:8][bytes…]` (packed bytes) |

## Heap and reference counting

Heap cells come from a 1 GiB anonymous `mmap` arena reserved on the first allocation. Every cell has a 16-byte header `[size:8][refcount:8]`; the pointer handed around points just after it.

- `__alloc` rounds the size up to 8, takes an exact-size cell from the free list or bumps the arena pointer, and sets the count to 1. The free list is one list searched linearly ([[MYLA-16]]); exhausting the arena traps.
- `__free` pushes the cell onto the free list.
- **Retain** (`_retain`) increments the counts of every heap pointer a value owns: list/map/builder cells, boxed enum cells, closure environments, recursively through inline aggregates (`_emit_owned_walk`).
- **Drop** (`_drop_value`) calls the per-type drop helper of each owned pointer: `__drop_list_<T>`, `__drop_map_<K>_<V>`, `__dropb_<Enum>`, `__sb_drop`, `__func_drop`. A helper decrements the count and, at zero, drops the children and frees the cell.
- **Ownership rules.** A local owns its value; binding copies and retains. Parameters are borrowed: they are never dropped by the callee. Owning locals are recorded per scope (`_drop_scopes`) and dropped at scope exit, before `return` (`_emit_return_drops`) and on `break`/`continue` (`_emit_loop_exit_drops`). Owning temporaries (a call's result, a literal) are dropped when their statement ends (`_drop_expr_temps`). A `for` loop retains the list or map it iterates for the duration of the loop.
- **Copy-on-write.** A write through a place (`xs[i] = v`, `push`, `m[k] = v`, `remove`, `append`) first finds the slot that holds the cell pointer, then `_cow_unique` clones the cell if its count is above 1 and stores the clone back. Clones retain the elements they now share.
- Match bindings and the match's copy of the scrutinee are borrowed without a retain, which is unsound when an arm writes to the scrutinee's variable ([[MYLA-2]]). Assigning a heap-owning aggregate to anything but a plain variable isn't implemented ([[MYLA-3]]).

The burn tests run allocate-and-drop loops of millions of cells to prove memory is reclaimed ([[Development/Testing]]).

## Closures

A capturing lambda allocates an environment cell: word 0 holds a drop function (`myla_<lifted>_env_drop`, or `__free` when no capture owns heap), the captured values follow, copied and retained. Lambda bodies are emitted as separate functions `myla___lambda_<n>` whose hidden first argument is the environment; a captured name compiles to a load through it. `__func_drop` decrements the environment's count and tail-calls the stored drop function at zero.

## Runtime helpers

| Group | Helpers |
| --- | --- |
| Process | `_start`, `__trap` (exit 1), `__panic` (message to stderr, exit 1) |
| Printing | `__print_int`, `__print_uint`, `__print_bool`, `__print_str`, `__print_nl`, `__float_to_str`, `__char_to_str` |
| Strings | `__str_eq`, `__str_concat`, `__int_to_str`, `__uint_to_str`, `__bool_to_str`, `__str_chars` (UTF-8 decode) |
| Heap | `__heap_init`, `__alloc`, `__free`, `__func_retain`, `__func_drop` |
| Collections | per type: `__drop_list_T`, `__clone_list_T`, `__grow_list_T` (doubling, minimum 4); `__new_map_*`, `__put_map_*`, `__find_map_*`, `__clone_map_*`, `__grow_map_*`, `__drop_map_*`, `__keys_map_*`, `__remove_map_*` (rebuilds the table); `__sb_new`, `__sb_drop`, `__sb_clone`, `__sb_grow`, `__sb_extend`, `__sb_build` |
| I/O | `__write`, `__args`, `__read_file` (open/fstat/read loop/close), `__write_file` (open O_WRONLY\|O_CREAT\|O_TRUNC 0644, write loop) |
| Processes | `__run`: builds a C argv, creates stdout, stderr and an O_CLOEXEC "exec error" pipe, forks, `dup2`s and `execve`s in the child; the parent drains both pipes with `poll`, reads the exec-error pipe to learn execve's errno, and decodes the `wait4` status into exit code or signal |
| Floats | `__fmod` (x87 `fprem`), `__two_prod` (Dekker), `__fscale`, and the power-of-ten tables `__pow10_hi`/`__pow10_lo` |

System calls used: read 0, write 1, open 2, close 3, fstat 5, poll 7, mmap 9, pipe 22, dup2 33, fork 57, execve 59, exit 60, wait4 61, pipe2 293.

## Float formatting

`print` and `format` render floats with an algorithm both back ends share ([[src/myla/types.py#L353-L465]]): find the decimal exponent by binary search over a table of powers of ten, scale the value to a 9- or 17-digit integer using double-double arithmetic (Dekker's exact product with a high/low power-of-ten table), round half to even, renormalise, trim trailing zeros and lay the digits out positionally. The assembly version uses the same constants and the same operation order, so the output is byte-identical to the interpreter's.

## Integer details

- `/` and `%` test the divisor for zero (`jz __trap`), then use `idivq` (signed, after `cqo`) or `divq`. `int64` minimum divided by -1 faults ([[MYLA-5]]).
- Shift counts are masked to `width - 1` before `shl`/`sar`/`shr`.
- Comparisons pick signed (`setl`…) or unsigned (`setb`…) instructions from the left operand's type; `char` compares unsigned.
- Float → integer casts use `cvttsd2si`, which gives the "integer indefinite" value for NaN and out-of-range inputs ([[MYLA-6]]); `uint64` → float handles the high bit with a halving trick.
