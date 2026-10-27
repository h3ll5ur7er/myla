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
| [[selfhost/lower.my]] | `impl CodeGen`: the checked AST of one function → `IrFunc`, or the construct it can't lower yet |
| [[selfhost/ir_x86.my]] | `impl CodeGen`: `IrFunc` → assembly, with the frame layout, through the code generator's `emit`, pools and debug information |

`impl CodeGen` blocks in other modules (allowed since an `impl` follows its type) give the IR code the code generator's state without a second copy of it, and keep [[selfhost/codegen.my]] almost unchanged until the old path is removed. In `generate`, a function job with `--ir` tries `lower_function`; `Ok` goes to `emit_ir`, `Err` (the unsupported construct, which `--ir-stats` reports) to `gen_function` as today.

## The IR

### Functions, blocks, values

A function has parameters, a result, slots, temporaries and basic blocks; block 0 is the entry. Every block ends in exactly one terminator.

- **Temporaries** `%tN` hold one scalar (8 bytes). Each has a kind.
- **Slots** `$sN` are frame memory: a size, an alignment, a Myla type for drops and debug information, and whether the slot **owns** its value (a local, a staged value, an owning temporary such as a call's aggregate result). Locals that are scalars are slots too (8 bytes), so their address can be taken and the debugger finds them.
- **Parameters** keep the calling convention: argument *i* is the 8-byte word at `16 + 8*i(%rbp)` (after the hidden result pointer, when there is one); an aggregate argument is a pointer to the caller's storage. `param i` reads that word.

### Instructions

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

Terminators:

```text
jmp L3
br %c, L4, L5
ret                           ret %t
trap index @pos               ; the runtime error at a position (never returns)
unreachable
```

`T` is a Myla type (`[str]`, `Option<Point>`); the backend turns `retain`/`drop`/`cow` into the same walks and helper calls the current code generator emits (`owned_walk`, `__drop_list_T`, `__cow…`). Positions (`@pos`) are the 16-byte records of runtime errors ([[Architecture/Native-backend#runtime-error-positions]]), shared with the old path.

### Ownership in the IR

The lowering makes every rule of [[Architecture/Native-backend#heap-and-reference-counting]] an instruction: a binding copies and retains; parameters are borrowed; owning slots are dropped at scope exit, before `ret` and on loop exits; staged stores evaluate the value into an owning slot, then `cow` the container and move the value in; match bindings borrow from the match's copy of the scrutinee, retained when an arm may write the variable it came from. The **verifier** follows each owning slot along every path (uninitialised → owned → moved or dropped) and rejects a drop of a slot that isn't owned, an owned slot still live at `ret` or at a block's exit when the successor disagrees, and a read of a moved slot. It runs on every function the gates compile.

### Text form

`gen_main <file> <stdlib> --emit-ir` prints every IR function, for tests and debugging:

```text
fun myla_add_one(i32) -> i32 {
  slots: $s0 n: i32 (8)
L0:
  loc 2 5
  %t0 = param 0
  store i64 [$s0], %t0
  bind n $s0
  loc 3 5
  %t1 = load i64 [$s0]
  %t2 = const i32 1
  %t3 = add i32 %t1, %t2
  ret %t3
}
```

## The backend

`emit_ir` lays out the frame (each slot its offset, each temporary an 8-byte slot of its own at first, exactly as wasteful as today), then emits each block: a label per block, one short instruction sequence per IR instruction, the prologue and epilogue as `gen_function` emits them. `loc` becomes `.loc` (with `-g`), `bind` the DWARF variable and scope entries through the existing `dbg_*` methods.

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
