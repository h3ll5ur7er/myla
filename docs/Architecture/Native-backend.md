# Native backend

[[src/myla/compiler/codegen_x86.py]] turns the monomorphized program ([[Architecture/Monomorphization]]) into GAS/AT&T assembly for x86-64 Linux. [[src/myla/compiler/__init__.py]] writes `<out>.s`, runs `as --64` and `ld`, and deletes the intermediate files (`--keep-asm` keeps the `.s`). There is no libc: the runtime is emitted as assembly and talks to the kernel with system calls (D2, D29).

The self-hosted code generator ([[Architecture/Self-hosted-compiler]]) began as a port of this one and uses the same conventions and layouts; since [[MYLA-107]] it emits every function from its IR ([[Architecture/IR]]) instead of in one pass.

[TOC]

## Strategy

- One pass per function, no IR, no register allocation. Every expression leaves its result in `%rax`; binary operators evaluate the left operand, push it, evaluate the right, and leave the left in `%rax` and the right in `%rcx` (left to right, [[MYLA-8]]). When one operand is a literal, whose evaluation can't be observed, they use the shorter right-first sequence instead (`_eval_operands`).
- Before emitting a function, `_layout_frame` walks its body and gives **every** local, temporary, match binding, loop counter and scratch value its own `%rbp`-relative slot, keyed by node id. Slots are never reused; the frame is rounded up to 16 bytes.
- Runtime helpers are emitted only when used (flags such as `_uses_float`, `_uses_run`).

## Calling convention

Internal and stack-based (never called from C):

- Argument *i* is at `16 + 8*i(%rbp)`; the callee pops the arguments (`ret $8n`, `_ret_popping`), so `become` can replace a function by one taking more arguments (D87). To evaluate them left to right, the caller reserves the argument words and stores each argument in source order (`_store_call_words`). When at most one argument isn't a literal, the order can't be observed, and it pushes them last to first instead, which is shorter.
- Scalars (integers, floats as their f64 bit pattern, `char`, `bool`, `str` pointers, list/map/builder pointers) are passed by value in one 8-byte slot.
- Aggregates (structs, tuples, enums, function values) are passed as a **pointer** to the caller's storage, but for a struct, tuple or enum parameter that a `become` hands one over to (the checker's `become_handovers`, D88): its words are copied into the argument words with references of their own (`_param_byval`, the `("value", …)` items of `_store_call_words`), and the callee binds it as a local there and drops it. This is safe because parameters are immutable; a `var self` receiver is passed the same way, so writes reach the caller. A method writing its receiver gets a copy of an argument read from the receiver's variable instead, as its writes would show through the pointer (`_aliased_args`, [[MYLA-123]], [[MYLA-129]]).
- An aggregate result uses a hidden first argument (sret): a pointer to storage the caller reserved, returned again in `%rax`.
- Function values are called as `code_ptr(env_ptr, args…)`; plain functions used as values get a `myla_<fn>__fnval` adapter that drops the env argument by moving the return address (and the sret pointer) over it and jumps to the function.
- `become f(args)` (D87, `_gen_become`) pushes the words as a call does, drops the statement's temporaries and every owner, moves the words into the function's own with the return address below them (`_frame_handover`) and jumps; the callee returns to the function's caller.

`_start` stores `argc`, `argv` and `envp`, calls `myla_<entry>`, then exits 0. All user functions are labelled `myla_<name>`.

## Value layout

| Type | Representation |
| --- | --- |
| integers, `char`, `bool` | One 8-byte slot holding the **canonical 64-bit value**: signed types sign-extended, unsigned zero-extended. After arithmetic `_wrap` re-canonicalises (`shl`/`sar`, `movl`, or `and`) |
| floats | The IEEE double bit pattern in a general register; arithmetic in `%xmm0`/`%xmm1`; `float32` is rounded with `cvtsd2ss`/`cvtss2sd` after each operation |
| `str` | Pointer to `[len:8][bytes…]`, a reference-counted heap cell (D62, [[MYLA-18]]). Literals and the renderers' constants (`true`, `nan`, …) are cells in `.data` with the same header and a count of 2^62 (`STATIC_RC`), which retains and drops change but never bring to zero, so they need no special case |
| struct | Fields inline, each in its stored size, in declaration order |
| tuple | Elements inline |
| enum | `[tag:8][payload union]`: the tag is the variant's index; the payload area is as large as the largest variant. A derived `eq` compares tags first; on an enum without payloads both backends emit only that comparison (the Python backend replaces the checker's synthesized `match`, [[MYLA-87]]) |
| boxed (recursive) enum, as a member | An 8-byte pointer to a heap cell holding the inline enum value |
| function value | 16 bytes: `(code_ptr, env_ptr)`; `env_ptr` is 0 when nothing is captured |
| list `[T]` | Pointer to a heap cell `[len:8][cap:8][elem…]`, stride = the element's stored size |
| map `[K: V]` | Pointer to `[len:8][cap:8][slot…]`, slot = `[state:8][key:8][value]`, state 0 empty / 1 occupied; open addressing with linear probing, FNV-1a hash of the key bytes (string contents for `str`), capacity a power of two kept under 0.75 load. A map holds a reference to each `str` key: `__put_map` retains a key it inserts, rehashing (`grow`, `remove`) moves keys, and `drop`, `clone` and `keys` treat keys like values |
| `StringBuilder` | Pointer to `[len:8][cap:8][bytes…]` (packed bytes) |

## Heap and reference counting

Heap cells come from a 1 GiB anonymous `mmap` arena reserved on the first allocation. Every cell has a 16-byte header `[size:8][refcount:8]`; the pointer handed around points just after it.

- `__alloc` rounds the size up to a multiple of 8 (at least 8), takes a free cell of exactly that size or bumps the arena pointer, and sets the count to 1. Exhausting the arena traps.
- Free cells up to 4 KiB (`_SMALL_CELL_LIMIT`) sit on one LIFO list per 8-byte size class (`__free_buckets`, indexed by the size itself as a byte offset), so allocating and freeing them is O(1); a larger cell is rounded up to a power of two and has one list per power after those, as in the self-hosted runtime. Before this (MYLA-16) all cells shared one scanned list, which made bootstrap stage 2 take four minutes instead of a second; until [[MYLA-80]] larger cells shared one list searched for an exact fit, so a cell of a size never requested again stayed unused for good, and a long-running program (the language server) grew with every check.
- `__free` pushes the cell onto its list. It clobbers only `%rax`: drop sequences walk aggregates through other caller-saved registers across calls that end in `__free`.
- **Retain** (`_retain`) increments the counts of every heap pointer a value owns: `str`/list/map/builder cells (`_CELL_TYPES`), boxed enum cells, closure environments, recursively through inline aggregates (`_emit_owned_walk`).
- **Drop** (`_drop_value`) calls the per-type drop helper of each owned pointer: `__str_drop`, `__drop_list_<T>`, `__drop_map_<K>_<V>`, `__dropb_<Enum>`, `__sb_drop`, `__func_drop`. A helper decrements the count and, at zero, drops the children and frees the cell.
- **Ownership rules.** A local owns its value; binding copies and retains. Parameters are borrowed: they are never dropped by the callee, but for the ones a `become` hands a heap value over to (the checker's `become_handovers`, D87), which the callee owns and drops and every caller gives a reference of its own (`_param_owned`). Owning locals are recorded per scope (`_drop_scopes`) and dropped at scope exit, before `return` (`_emit_return_drops`) and on `break`/`continue` (`_emit_loop_exit_drops`). Owning temporaries (a call's result, a literal, a `match` expression's value) are dropped when their statement ends (`_drop_expr_temps`). Where no statement end follows, they are dropped as soon as the value is computed: an `if` or `while` condition, a match guard, a range bound, and each operand of `&&`/`||`, whose right side may not run (`_eval_scalar`). A match registers its scrutinee's temporaries with its drop scope, so an arm that leaves early (`return`, `break`, `continue`, a failing `?`) drops them too. Until [[MYLA-74]] none of these were released, which leaked memory and, by keeping counts above 1, made copy-on-write copy on every write. A `for` loop retains the list or map it iterates for the duration of the loop.
- **Stores** of a heap-owning value (any assignment, MYLA-3) and all stores into containers (`push`, `xs[i] = v`, `m[k] = v`, `append_byte`, and a map literal's values, each after its key) evaluate the value first, into a frame slot that owns one reference (`_stage_value`), and only then find, unshare and grow the container, release the old value and move the new one in (`_commit_staged`). That is the interpreter's order: a `?` inside the value leaves the container untouched, `push(xs, pop(xs))` and `xs[i] = xs[i]` work, and until the commit an early return releases the staged value (MYLA-4). The self-hosted code generator does the same.
- **Boxed elements.** A list of a recursive enum holds boxes; `pop` copies the value out of the box, retains what it owns and releases the box ([[MYLA-74]]).
- **Copy-on-write.** A write through a place (`xs[i] = v`, `push`, `m[k] = v`, `remove`, `append`, and a field assignment at any depth such as `xs[i].f.g = v`) first finds the slot that holds the cell pointer, then `_cow_unique` clones the cell if its count is above 1 and stores the clone back; `_mut_place_addr` does this for every container on the path to the place. Clones retain the elements they now share.
- **Match bindings** borrow from the match's copy of the scrutinee. When an arm may write to the variable the scrutinee comes from (an assignment to or into it, a mutating builtin on it, or a method call on it, found by `_may_write`), that copy is retained for the duration of the match, so the write copies on write instead of changing or freeing what the bindings see (MYLA-2). Otherwise nothing is retained: Myla has no references and closures capture by value, so nothing else can change the scrutinee during the match. The self-hosted code generator makes the same decision (`arms_may_write`).

The burn tests run allocate-and-drop loops of millions of cells to prove memory is reclaimed ([[Development/Testing]]).

## Closures

A capturing lambda allocates an environment cell: word 0 holds a drop function (`myla_<lifted>_env_drop`, or `__free` when no capture owns heap), the captured values follow inline (a recursive enum too, like a variable holds it), copied and retained. Lambda bodies are emitted as separate functions `myla___lambda_<n>` whose hidden first argument is the environment; a captured name compiles to a load through it. `__func_drop` decrements the environment's count and tail-calls the stored drop function at zero.

## Runtime helpers

| Group | Helpers |
| --- | --- |
| Process | `_start`, `__panic` (`runtime error: <message>` and the position to stderr, exit 1; `__write_err`, `__write_err_num` write its parts), the runtime-error entries `__trap_index`, `__trap_key`, `__trap_pop`, `__trap_div`, `__trap_mod`, `__trap_match`, `__trap_oom` (each passes its message to `__panic`, [[MYLA-17]]; see below), `__write_all` (loops over short writes, retries `EINTR`/`EAGAIN`; every output goes through it) |
| Printing | `__print_int`, `__print_uint`, `__print_bool`, `__print_str`, `__print_nl`, `__float_to_str`, `__char_to_str` |
| Strings | `__str_eq`, `__str_concat`, `__int_to_str`, `__uint_to_str`, `__bool_to_str`, `__str_chars` (UTF-8 decode; U+FFFD for each byte outside a well-formed sequence) |
| Heap | `__heap_init`, `__alloc`, `__free`, `__func_retain`, `__func_drop` |
| Collections | per type: `__drop_list_T`, `__clone_list_T`, `__grow_list_T` (doubling, minimum 4); `__new_map_*`, `__put_map_*`, `__find_map_*`, `__clone_map_*`, `__grow_map_*`, `__drop_map_*`, `__keys_map_*`, `__remove_map_*` (rebuilds the table); `__sb_new`, `__sb_drop`, `__sb_clone`, `__sb_grow`, `__sb_extend`, `__sb_build` |
| I/O | `__write`, `__read` (one read into a fresh str cell of capacity n, retried on EINTR; [[MYLA-78]]), `__args`, `__read_file` (open/fstat/read loop/close), `__write_file` (open O_WRONLY\|O_CREAT\|O_TRUNC 0644, write loop), `__list_dir` (open O_DIRECTORY, getdents64 into a 4 KB stack buffer, names appended to a str cell that doubles when full), `__mkdir`, `__stat` (`st_mode` from stat(2)); the three share a path copy onto the stack ([[MYLA-88]]) |
| Processes | `__run`: builds a C argv, creates stdout, stderr and an O_CLOEXEC "exec error" pipe, forks, `dup2`s and `execve`s in the child; the parent drains both pipes with `poll`, reads the exec-error pipe to learn execve's errno, and decodes the `wait4` status into exit code or signal |
| Floats | `__fmod` (x87 `fprem`), `__two_prod` (Dekker), `__fscale`, and the power-of-ten tables `__pow10_hi`/`__pow10_lo` |

System calls used: read 0, write 1, open 2, close 3, fstat 5, poll 7, mmap 9, pipe 22, dup2 33, fork 57, execve 59, exit 60, wait4 61, pipe2 293.

## Runtime-error positions

A runtime error prints the interpreter's first two lines: `runtime error: <message>` (without the values) and `  --> file:line:col`, the position of the node the interpreter reports for the same error ([[MYLA-65]], D75). It works in every build, not only with `-g`:

- Each position a trap can report has a 16-byte record in `.rodata`, `[file str:8][line:4][col:4]`, where the file is a static `str` cell (shared with literals of the same text); records are shared by all traps at one position (`_load_position`).
- A check jumps over a call to the trap entry (`_trap`): `cmpq %rdx, %rax; jb .L7; leaq .Lpos3(%rip), %rsi; call __trap_index; .L7:`. The common case falls through one taken branch. The `call` (it never returns) leaves a return address, so under gdb `break __panic` then `bt` shows the Myla frame and line, and `up` shows its variables.
- `__trap_<kind>` loads its message into `%rdi` and jumps to `__panic`, which writes the prefix, the message and, when `%rsi` isn't 0, the position. `panic`, `assert` and `unreachable` call `__panic` with their message and the call's record. `__trap_oom`, reached from `__alloc`, has no position.
- `append(sb, s, start, end)` checks its range inside `__sb_extend_range`; the caller passes the record in `%r8`.
- The file is named as the compiling CLI names it in diagnostics: the entry file as given (`build(…, entry_path=…)`, which `myla build` passes), another module relative to the working directory (`_display_path`); without an entry path (API callers) the loader's absolute path, without any (a program compiled from text) `<input>`. The self-hosted backend names files as its loader does (`set_sources`, `path_of`), which is the same for paths given relative to the working directory.

## Float formatting

`print` and `format` render floats with an algorithm both back ends share ([[src/myla/types.py#L353-L465]]): find the decimal exponent by binary search over a table of powers of ten, scale the value to a 9- or 17-digit integer using double-double arithmetic (Dekker's exact product with a high/low power-of-ten table), round half to even, renormalise, trim trailing zeros and lay the digits out positionally. The assembly version uses the same constants and the same operation order, so the output is byte-identical to the interpreter's. Two details keep it exact at the ends of the range (MYLA-29): an operand above 2^996 would overflow Dekker's split, so `two_prod` first scales it down by 2^64 and the other operand up (both exact); and for magnitudes below about 10^-292, which are scaled by 10^200 first, the intermediate stays a double-double. The self-hosted backend embeds this runtime verbatim (`scripts/gen_selfhost_runtime.py` generates it from the Python code generator; a unit test checks they match).

## Debug information

`myla build -g` adds DWARF debug information; without `-g` the output is unchanged. See [[Development/Debugging]] for what gdb shows.

- **Line table** ([[MYLA-71]]): `.file`/`.loc` directives, one `.file` per source module (the loader records each function's `source_path`), a `.loc` at each function's label, before every statement and before each expression-bodied match arm, and `.loc <file> 0 0` after each function so the runtime helpers emitted later have no source line. The assembler turns them into the `.debug_line` table. Lambdas take the file of the function they are created in.
- **Variables and types** ([[MYLA-66]], D75): [[src/myla/compiler/dwarf.py]] writes `.debug_abbrev` (a fixed table) and one compile unit in `.debug_info`, whose `DW_AT_stmt_list` points at a label opening `.debug_line`, where the assembler puts its table. The unit's language is Rust, whose printing rules and expression syntax suit Myla. The code generator streams the DIEs while it walks a function: `begin_function` opens a subprogram (its label, `myla_<name>`, frame base `%rbp`, and its result type for `finish`: a scalar's or cell pointer's type read from `%rax`, a pointer to an aggregate result, which `%rax` holds after the hidden-pointer return, none for a float result, which is in `%rax` where gdb reads `%xmm0`); every name bound in a scope goes through `_bind` (parameters and captures for the whole function; another binding opens a lexical block at a label emitted after its value is stored, ending at a label emitted when its Myla scope closes, `_push_scope`/`_pop_scope`), so shadowing and scopes are exact. Locations follow the scope entries: `DW_OP_fbreg off` for a local, plus `DW_OP_deref` for an aggregate parameter or a borrowed aggregate loop variable, through the environment for a capture. Types are emitted once each, after the subprograms: base types (a signed integer as its whole 8-byte slot, so gdb writes it sign-extended), structs, tuples (fields `__0`, …), enums as Rust variant parts (a `<tag>` discriminant and one variant struct per tag), function values; a `str` or builder variable is a Rust `&str` made of two computed pieces, a list variable an array at its elements with a count read from the header (`DW_OP_push_object_address`), a `float32` variable the double it is kept as, converted (`DW_OP_GNU_deref_type`, `DW_OP_GNU_convert`). Inside aggregates and lists a heap value is a pointer to a description of its cell (`len`, `cap`, the bytes or items as an array sized from the header, a map's `slots` `[state][key][value]` as many as its capacity), since gdb accepts only fixed-size types there. Generic instances get their Myla names (`Option<int32>`) from the monomorphizer's `type_display_names`.
- **Pretty-printers** ([[MYLA-66]], D82): [[src/myla/debug/myla_gdb.py]] is embedded in every `-g` binary as an inline Python script (kind 4) in `.debug_gdb_scripts` (`"MS",@progbits,1`: the byte 4, the name `myla-printers` and a newline, the file's text as `.ascii` lines, a NUL). The Python backend reads it next to the compiler package; the self-hosted one reads `<stdlib root>/debug/myla_gdb.py` (`dwarf.read_gdb_script`, called by `gen_main` and the CLI driver, passed to `enable_debug_info`); both write the same bytes. gdb runs it on loading the binary where `auto-load safe-path` allows; it registers a global printer `myla` that recognises the cell types by name and fields (`str`, `StringBuilder`, `[T]` with `items`, `[K: V]` with `slots`), pointers to them, pointers to structs and enums (boxed enums, aggregate results), and the 8-byte base type `float32`. Cells print as their text, elements or entries, the rest as the value pointed at or a float. The script must stay ASCII.

## Integer details

- `/` and `%` test the divisor for zero (`jz __trap_div` / `__trap_mod`), then use `idivq` (signed, after `cqo`) or `divq`. A signed divisor of -1 skips `idivq` (which faults on the minimum): `/` negates and `%` gives 0, so the result wraps ([[MYLA-5]]).
- Shift counts are masked to `width - 1` before `shl`/`sar`/`shr`.
- Comparisons pick signed (`setl`…) or unsigned (`setb`…) instructions from the left operand's type; `char` compares unsigned.
- Float → integer casts saturate (D59): NaN (`ucomisd` sets the parity flag) gives 0, inputs at or beyond the target's bounds give its minimum or maximum, the rest go through `cvttsd2si`; a `uint64` from 2^63 up converts `x - 2^63` and sets the top bit. `uint64` → float handles the high bit with a halving trick.
