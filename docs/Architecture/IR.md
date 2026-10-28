# IR

The design of the mid-level intermediate representation between the checker and the self-hosted native backend ([[MYLA-67]], D79). Today [[selfhost/codegen.my]] turns the checked, monomorphized AST straight into assembly text and decides frame layout, reference counting, copy-on-write, staged stores and drops while it emits instructions ([[Architecture/Native-backend]]). The IR makes those decisions explicit data, so they can be printed, checked and optimised, and leaves the backend only instruction selection.

> [!NOTE]
> **Status: approved, being built.** The decisions below were approved on 2026-10-27 (D79). The steps are tasks [[MYLA-103]] to [[MYLA-109]].

[TOC]

## Decisions

1. **Self-hosted backend only.** The Python backend ([[src/myla/compiler/codegen_x86.py]]) stays as it is: the bootstrap's stage 1 and the independent reference the gates compare with (D71). Building the IR into both would double the work, and two backends that share an IR stop being independent checks of each other.
2. **Three-address code on basic blocks, not SSA.** Instructions read and write virtual temporaries (`%t3`) and frame slots (`$s2`); a temporary may be assigned more than once. It is the simplest form to lower the AST into, registers can still be allocated over temporaries, and SSA can be built on top later if an optimisation wants it.
3. **Close to the machine.** Scalars are 8-byte values with an explicit kind (`i8`…`i64`, `u8`…`u64`, `f32`, `f64`, `bool`, `char`, `ptr`); integer operations carry their type and re-canonicalise as today (sign- or zero-extended in 64 bits, [[Architecture/Native-backend#integer-details]]). Aggregates (structs, tuples, enums, function values) live in slots of a given size and are reached through addresses; loads and stores take explicit offsets. Reference counting is explicit: `retain`, `drop`, `cow`. The IR is monomorphic: generic functions are instantiated before lowering, as now.
4. **The runtime stays.** The allocator, strings, maps, builders, printing, traps and system calls stay handwritten assembly, emitted as today. The IR calls them; only user code (functions, lambdas, adapters) goes through the IR.
5. **Migration behind a flag, function by function.** `--ir` makes the backend lower each function to IR and emit it from there; a function using a construct the lowering doesn't support yet falls back to the current path. Both paths share the calling convention, the frame base, the runtime and the code generator's pools (string literals, position records, helper flags, debug information), so functions from either path call each other. The gates run the corpus with and without `--ir`; `--ir-stats` counts the functions each path emitted. When every function of the compiler itself goes through the IR, the parity corpus and the stress tests agree and the bootstrap reaches its fixed point, `--ir` becomes the default and the old emission code is deleted.
6. **First reach parity, then optimise.** The first target is identical behaviour (the same output and exit status on every test, not the same assembly), a verifier that checks reference counting on every path, and a text form (`--emit-ir`). Optimisations come afterwards, each a task of its own, measured on the compiler compiling itself.
7. **No IR interpreter yet.** The verifier plus the comparison of native output with the interpreters is the oracle; an IR interpreter can come later if bugs call for it.

## Modules

| Module | Role |
| --- | --- |
| [[selfhost/ir.my]] | The data types (`IrFunc`, `Block`, `Inst`, `Operand`, `Kind`), the text printer (`render_func`) and the verifier |
| [[selfhost/lower.my]] | The checked AST of one function or lambda → `IrFunc` (`lower_function`, `lower_lambda`), reading the code generator |
| [[selfhost/ir_x86.my]] | `impl CodeGen`: `IrFunc` → assembly, with the frame layout, through the code generator's `emit`, pools and debug information |

`impl CodeGen` blocks in other modules (allowed since an `impl` follows its type) give the IR code the code generator's state without a second copy of it. In `generate`, each function job goes through `lower_function`, the verifier and `emit_ir` (`gen_any_function`, `take_ir`), and each lambda job through `lower_lambda` (`gen_any_lambda`). Since [[MYLA-107]] there is no other path: a function the lowering can't take, or the verifier rejects, is an internal error. During the migration such a function fell back to the old one-pass emission, which [[MYLA-107]] deleted.

## The IR

### Functions, blocks, values

A function has parameters, a result, slots, temporaries and basic blocks; block 0 is the entry. Every block ends in exactly one terminator.

- **Temporaries** `%tN` hold one scalar (8 bytes). Each has a kind.
- **Slots** `$sN` are frame memory: a size, an alignment, a Myla type for drops and debug information, and whether the slot **owns** its value (a local, a staged value, an owning temporary such as a call's aggregate result). Locals that are scalars are slots too (8 bytes), so their address can be taken and the debugger finds them.
- **Parameters** keep the calling convention: argument *i* is the 8-byte word at `16 + 8*i(%rbp)` (after the hidden result pointer, when there is one); an aggregate argument is a pointer to the caller's storage. `param i` reads that word.

### Instructions

What [[MYLA-103]], [[MYLA-104]] and the first two parts of [[MYLA-105]] built is marked *now*; the rest is the plan for the next steps.

```text
%t = const i32 42             %t = const f64 0x400921fb54442d18
%t = str "text"               ; the address of a static str cell
%t = fn myla_name             ; the address of a code label
%t = param 0                  ; the argument word
%t = addr $s3 + 8             ; the address of a slot (plus an offset)
%t = load i64 [%p + 16]       store i64 [%p + 16], %v
copy 24 [%dst], [%src]        zero 24 [%dst]
%t = add i32 %a, %b           ; also sub mul and or xor shl shr; wraps to i32
%t = div i32 %a, %b @pos      ; rem too: traps on zero at the position
%t = neg i32 %a               %t = not bool %a
%t = cmp lt i32 %a, %b        ; eq ne lt le gt ge, signedness from the kind
%t = cast f64 -> i32 %a       ; saturating float → int, as today
%t = call myla_f(%a, %p)      ; a user function; aggregates by address
call myla_f sret %r (%a)      ; an aggregate result into the storage at %r
%t = callv %code, %env (%a)   ; a function value
%t = rt __str_concat(%a, %b)  ; a runtime helper, in its own registers
retain T [%p]                 ; every heap pointer the T at %p owns
drop T [%p]                   ; release them (the per-type drop helpers)
cow T [%p]                    ; make the cell at %p unique before a write
loc 12 5                      ; the source position of what follows
bind x $s3                    ; debug information: x lives in $s3 from here
```

*Now*: `const`, `str`, `load`/`store` of 8-byte slots, `addr` (a slot's address), `%t = %p + off`, `load`/`store` at `[%p + off]`, `copy size [%dst], [%src]`, `call … sret %r` (an aggregate result into the storage at `%r`), `rt name(%args)` (a runtime helper such as `__str_concat`, the arguments in `%rdi`, `%rsi`, …), `retain T %v` (a cell) and `retain T [%p]` (every heap value of the T at `%p`), `drop T $slot` (an owner's end) and `drop T [%p]` (a member before it is overwritten), `init $slot` (an aggregate built member by member is complete; no code), `elem %cell[%i] stride` (an element's or byte's address, bounds-checked at a position), `load8`, `cow T [%holder]` (the cell made unique, a clone stored back when shared), `append [%holder] %cell stride` (room for one more element, the grown cell stored back), `pop %cell stride` (the last element's address, trapping when empty), `%t, %t2 = rt name(%args)` (a helper returning `%rax` and `%rdx`: `__map_set_slot`'s slot and whether the key was there), `check %v kind` (trap when `%v` is 0: a missing map key), `sbappend`/`sbappendbyte`/`sbbuild` (the builder sequences), `mapremove T [%holder] %cell %key`, `global sym width` (a runtime variable such as `__io_errno_val`), `exit %code`, `moved $slot` (an owning slot's value was moved into a container; no code, for the verifier), `label sym` (a code address), `call [%fv](%args)` and `call [%fv](%args) sret %r` (through a function value: its environment the word after the result's address), the integer and float operations (`%t = + int32 %a, %b`, with the result type after `->` when it differs, and `@line:col` on a division), `cmp`, the unary operators, `cast`, `call` with scalar arguments, `print ty %a` (a scalar, as `print` writes it), `loc`, `bind`, and `scope open`/`scope close` (the lexical scopes of debug information, which `emit_ir` turns into the same DWARF blocks as the old path).

Terminators (*now*: `jmp`, `br`, `ret`, `trap`, `panic`):

```text
jmp L3
br %c, L4, L5
ret                           ret %t
trap index @pos               ; the runtime error at a position (never returns)
panic %msg @pos               ; `panic`, `unreachable`, a failed `assert` (never returns)
unreachable
```

`T` is a Myla type (`[str]`, `Option<Point>`); the backend turns `retain`/`drop`/`cow` into the code generator's walks and helper calls (`owned_walk`, `__drop_list_T`, `__clone_list_T`); an enum's walk, or that of a struct or tuple with several owning members, is a helper of its own (`__walkd_T`, `__walkr_T`, [[MYLA-108]]). Positions (`@pos`) are the 16-byte records of runtime errors ([[Architecture/Native-backend#runtime-error-positions]]), shared with the old path.

### Ownership in the IR

The lowering makes every rule of [[Architecture/Native-backend#heap-and-reference-counting]] an instruction: a binding copies and retains; parameters are borrowed; owning slots are dropped at scope exit, before `ret` and on loop exits; staged stores evaluate the value into an owning slot, then `cow` the container and move the value in; match bindings borrow from the match's copy of the scrutinee, retained when an arm may write the variable it came from. The **verifier** follows each owning slot along every path (uninitialised → owned → moved or dropped) and rejects a drop of a slot that isn't owned, an owned slot still live at `ret` or at a block's exit when the successor disagrees, and a read of a moved slot. It runs on every function the gates compile.

### Text form

`gen_main <file> <stdlib> --emit-ir` prints every IR function, for tests and debugging:

```myla
fun scale(x: int32, by: int32) -> int32 {
    if x > 100 {
        return x
    }
    return x * by
}
```

```text
fun myla_scale -> int32 {
  $0 x: int32 (argument 0)
  $1 by: int32 (argument 1)
L0:
  bind x $0
  bind by $1
  scope open
  loc 2 5
  %t0 = load $0
  %t1 = const int32 100
  %t2 = cmp > int32 %t0, %t1
  br %t2, L1, L2
L1:
  scope open
  loc 3 9
  %t3 = load $0
  ret %t3
L3:
  scope close
  jmp L2
L2:
  loc 5 5
  %t4 = load $0
  %t5 = load $1
  %t6 = * int32 %t4, %t5 @5:14
  ret %t6
L4:
  scope close
  ret
}
```

A parameter is a slot at its argument word, so it needs no copy. The code after a `return` lands in a block nothing jumps to (`L3`, `L4`), as the old path emits dead code there too; blocks are printed and emitted in the order lowering started them, the source order, which keeps the debug information's scopes nested.

## The backend

`emit_ir` lays out the frame (each slot its offset, each temporary an 8-byte slot of its own, as wasteful as the old path), then emits each block: a label per block, one short instruction sequence per IR instruction, and the old path's prologue and epilogue. The sequences for operations, casts, `print`, the unary operators, element addresses, map removal and the builder's range check and `build` (`emit_int_op`, `emit_float_op`, `emit_cast`, `emit_unary`, `emit_print`, `emit_elem_addr`, `emit_map_remove`, `emit_sb_range`, `emit_sb_build`) were split out of the old path's emitters while both existed, so wrapping, traps and float rounding couldn't drift between the paths; together with the retain, drop and copy-on-write walks and the runtime they are what remains of it. `loc` becomes `.loc` (with `-g`), `bind` and `scope` the DWARF variable and scope entries through the existing `dbg_*` methods.

### Coverage

During the migration `gen_main <file> <stdlib> --ir-stats` reported how many functions went through the IR and, for each other one, the first construct the lowering didn't cover yet:

| After | Examples | The compiler |
| --- | --- | --- |
| [[MYLA-103]] (scalars) | 50 of 227 | 13 of 1,004 |
| [[MYLA-104]] (plain aggregates, generic calls) | 94 of 227 | 18 of 1,021 |
| [[MYLA-105]], first part (strings, ownership, the verifier) | 122 of 227 | 64 of 1,072 |
| [[MYLA-105]], second part (lists) | 145 of 227 | 178 of 1,079 |
| [[MYLA-105]], third part (maps, builders, `format`, the other builtins) | 184 of 227 | 273 of 1,099 |
| [[MYLA-105]], fourth part (recursive enums) | 198 of 227 | 1,007 of 1,108 |
| [[MYLA-106]], first part (`?`, destructuring) | 207 of 227 | 1,084 of 1,111 |
| [[MYLA-106]], second part (function values) | 227 of 227 | 1,119 of 1,119 |

With function values every function of the compiler, the examples and the parity and stress programs went through the IR, and the compiler built through it emitted exactly the assembly the normal build did. Lambda bodies followed ([[MYLA-106]], third part: 1,124 functions of the compiler, 1,459 of the CLI, 949 of the language server), and `-g` builds. [[MYLA-107]] then made the IR the only path. Besides the functions, the code generator emits the partial-application and function-value thunks (fixed adapters, requested by the lowering as generic instances are), the environments' release functions, the per-type drop and clone helpers and the runtime.

`lowerable` decides from `CodeGen.ir_blocked`, the structs and enums whose declarations the lowering can't take (with function values lowered, only those using `Self`), worked out once before the first function (`blocked_types`, a fixed point); a type is lowerable when it names none of them, type arguments included. Walking each type's declarations on every call had made the IR thirty times slower on the compiler (61 s against 1.8 s).

### Lowering ownership

[[MYLA-105]] lowers strings, and aggregates holding them, with every rule of [[Architecture/Native-backend#heap-and-reference-counting]] as an instruction:

- **Owners.** A local owns its value: binding it copies and retains (`retain`). It is registered with its scope, whose end drops it (`drop $slot`), and `return`, `break` and `continue` drop the owners of the scopes they leave.
- **Temporaries.** An owned temporary (a call's result, a concatenation, an aggregate literal holding a string, a `match`'s value) lives in an owning slot registered with the statement, which drops it at its end. Where no statement end follows, it is dropped right after the value is known: a condition, a guard, an operand of `&&`/`||`, a range bound, an arm's expression. `return`, `break` and `continue` also drop the temporaries of the statements they leave.
- **Borrowing.** Parameters and match bindings borrow; nothing drops them.
- **Assignments.** An assignment takes the new value (retains it, staged in a slot of its own for an aggregate) before it releases the old one (`drop $slot` for a local, `drop [%p]` for a member), which the new value may share (`p = p`, `o.a = o.a`).
- **Staged values.** A value bound for a container or a member (`xs[i] = v`, `m[k] = v`, `push(xs, v)`, `o.f = v`) is taken first, as the interpreter does (MYLA-4), into an owning slot registered with the statement; the place, the index or the key evaluated after it may still leave the function (`m[f()?] = v`), and then the statement's drops release it. Once it is stored, `moved $slot` hands its references over and the slot leaves the statement's temporaries.
- **`?`.** On success the payload is borrowed from the operand. On failure, the tag and the failure's payload (not the whole operand, MYLA-80) are copied into the result's storage and retained; the temporaries and owners are then dropped as for `return`.
- **Function values.** A function value is 16 bytes, its code and its environment (a cell whose first word is its release function, or null), retained and released through the environment as on the old path. A lambda copies its captures into a new environment with references of their own (D48), and its body (`lower_lambda`) copies them out into slots of its own at entry, borrowed as parameters are; a partial application evaluates its receiver, filled arguments and called function value into one; `>>` puts both function values into one for the runtime's `__compose_call`; a named function becomes its thunk with a null environment. The value is the statement's until it is stored. A call through one evaluates the callee first, then the arguments.
- **Destructuring.** Each name of `let (a, (b, _)) = …` is a variable of its own, holding a retained copy of its element.
- **Lists.** A list literal is a new cell, its elements stored with their own references, owned by the statement. Reading an element borrows it from the list (bounds-checked, `elem`). A write to an element (`xs[i] = v`, `xs[i].f = v`, at any depth) takes the value first, then makes every list on the path to the place unique (`cow`), as the old path's `mut_place_addr` does, then releases the old element. `push` takes the value, makes the list unique, grows it when full (`append`) and moves the value in; `pop` moves the last element out to the statement. A `for` loop over a list holds a reference of its own for the loop (dropped at its end, or by a `return` from the body) and borrows each element.
- **Maps.** A map literal is a new map owned by the statement, each key evaluated before its value. A read (`m[k]`, also inside `get`) borrows the value, trapping when the key is missing (`check … key`). `m[k] = v` takes the value first, makes the map unique, finds or makes the key's slot (`__map_set_slot`, which retains a string key), releases the value it held when the key was there, and moves the new one in; a write into a value (`m[k].f = v`, `push(m[k], x)`) makes the map unique and traps on a missing key, as the old path's `mut_map_value_addr`. `remove` makes the map unique and releases the key and value (`mapremove`); `keys`, and a `for` loop over a map, make a new list of the keys.
- **Recursive enums.** A recursive enum's value is inline in a variable, a parameter, a result and a match's copy, but a member (a field, payload, tuple, list element or map value) holds a pointer to a box, as on the old path. Reading such a member as an aggregate borrows the box's value (`unbox`, also in sub-patterns, which match against the box). Storing one makes a new box holding a retained copy (`box`, the old path's `box_value`); assigning it to a member releases the old box (`drop [%p]`), and `pop` copies the value out with references of its own before releasing the box.
- **Builders and `format`.** `StringBuilder()` is a new cell; `append` and `append_byte` make it unique first. `build`, `chars`, `format` (and so f-strings) and every rendered piece make new strings owned by the statement; unlike the old path, which releases each piece as soon as it is concatenated, the IR keeps them until the statement ends.
- **The I/O intrinsics.** Runtime helpers (`rt`) or runtime variables (`global`); a cell they return is a new reference (`__run_stderr` hands over the runtime's).
- **Matches.** A match copies its scrutinee; the copy owns references of its own (retained, dropped after the match or by an arm's early exit) only when an arm may write the variable the scrutinee came from (MYLA-2).

The **verifier** (`verify` in [[selfhost/ir.my]]) follows every owning slot along the reachable paths. It rejects a store into a slot that still holds a value, a drop of one that holds none, a slot holding a value at `ret`, and paths that join disagreeing on a slot. A `copy`, `call … sret` or `init` into an owning slot stores into it. A function it rejects falls back to the old path with the reason `IR verifier: …`, which the IR gate treats as a failure.

### Lowering aggregates

A value that owns no heap memory is *plain*: a scalar, or a struct, tuple or enum of plain values (not a recursive enum, whose members are boxed). [[MYLA-104]] lowers plain aggregates: the lowering keeps a temporary holding the aggregate's address, as the old path keeps it in `%rax`. A local is a slot of the aggregate's size; a parameter's slot is its argument word, which holds the caller's address (for `var self` too, so writes reach the caller); an aggregate result is written through the address the caller passes as the first word, which the function returns. Literals and constructors build their value in a slot of their own; fields and elements are `+ off` from their aggregate's address; a `match` copies its scrutinee into a slot and tests each arm's pattern against it, copying bindings out (one slot per name and arm, shared by the alternatives of `|`), and traps when no arm matches. The checker leaves assignment targets untyped, so the lowering derives a place's type from its slots, as the old path does from its bindings. A generic function's instance is named by the lowering and stamped out by the code generator once the caller is lowered (the lowering only reads the code generator).

## Steps

| Task | Step |
| --- | --- |
| [[MYLA-103]] | This page and D79; `ir.my` (types, printer); the `--ir`, `--ir-stats` and `--emit-ir` flags; lowering and emission of scalar functions (integers, floats, `bool`, `char`, locals, `if`/`while`/`for` over ranges, calls with scalar arguments and results, arithmetic traps) with the per-function fallback; the gates run the corpus with `--ir` |
| [[MYLA-104]] | Aggregates: structs, tuples, enums, `match` without heap values, aggregate parameters and results (sret), field and tuple access |
| [[MYLA-105]] | Heap values and ownership: strings, lists, maps, builders, `retain`/`drop`/`cow`, staged stores, drops at every exit; the verifier |
| [[MYLA-106]] | Closures and function values, partial application, `for` over lists and maps, `?`, the remaining builtins; `-g` through the IR (variables and scopes) |
| [[MYLA-107]] | Every function of the compiler through the IR; `--ir` the default; the old emission code deleted; the bootstrap's fixed point |
| [[MYLA-108]] | Optimisations, each measured on the compiler compiling itself: slot reuse, retain/drop pairs that cancel, scalars in registers, copy elision for results, dead functions |
| [[MYLA-109]] | Later: an LLVM backend on the IR ([[MYLA-62]]), an IR interpreter if needed |
