# IR

The design of the mid-level intermediate representation between the checker and the self-hosted native backend ([[MYLA-67]], D79). Today [[selfhost/codegen.my]] turns the checked, monomorphized AST straight into assembly text and decides frame layout, reference counting, copy-on-write, staged stores and drops while it emits instructions ([[Architecture/Native-backend]]). The IR makes those decisions explicit data, so they can be printed, checked and optimised, and leaves the backend only instruction selection.

> [!NOTE]
> **Status: built, and stable since D85.** The decisions below were approved on 2026-10-27 (D79). The steps were tasks [[MYLA-103]] to [[MYLA-109]] and [[MYLA-120]] to [[MYLA-122]]; see "Stability" for what may change from here.

[TOC]

## Decisions

1. **Self-hosted backend only.** The Python backend ([[src/myla/compiler/codegen_x86.py]]) stays as it is: the bootstrap's stage 1 and the independent reference the gates compare with (D71). Building the IR into both would double the work, and two backends that share an IR stop being independent checks of each other.
2. **Three-address code on basic blocks, not SSA.** Instructions read and write virtual temporaries (`%t3`) and frame slots (`$s2`); a temporary may be assigned more than once. It is the simplest form to lower the AST into, registers can still be allocated over temporaries, and SSA can be built on top later if an optimisation wants it.
3. **Close to the machine.** Scalars are 8-byte values with an explicit kind (`i8`…`i64`, `u8`…`u64`, `f32`, `f64`, `bool`, `char`, `ptr`); integer operations carry their type and re-canonicalise as today (sign- or zero-extended in 64 bits, [[Architecture/Native-backend#integer-details]]). Aggregates (structs, tuples, enums, function values) live in slots of a given size and are reached through addresses; loads and stores take explicit offsets. Reference counting is explicit: `retain`, `drop`, `cow`. The IR is monomorphic: generic functions are instantiated before lowering, as now.
4. **The runtime stays.** The allocator, strings, maps, builders, printing, traps and system calls stay handwritten assembly, emitted as today. The IR calls them; only user code (functions, lambdas, adapters) goes through the IR.
5. **Migration behind a flag, function by function.** `--ir` makes the backend lower each function to IR and emit it from there; a function using a construct the lowering doesn't support yet falls back to the current path. Both paths share the calling convention, the frame base, the runtime and the code generator's pools (string literals, position records, helper flags, debug information), so functions from either path call each other. The gates run the corpus with and without `--ir`; `--ir-stats` counts the functions each path emitted. When every function of the compiler itself goes through the IR, the parity corpus and the stress tests agree and the bootstrap reaches its fixed point, `--ir` becomes the default and the old emission code is deleted.
6. **First reach parity, then optimise.** The first target is identical behaviour (the same output and exit status on every test, not the same assembly), a verifier that checks reference counting on every path, and a text form (`--emit-ir`). Optimisations come afterwards, each a task of its own, measured on the compiler compiling itself.
7. **No IR interpreter yet.** The verifier plus the comparison of native output with the interpreters is the oracle; an IR interpreter can come later if bugs call for it.

## Stability

Since D85 the IR is stable: the instruction set, the terminators, the model of slots and temporaries and what each instruction means, as "The IR" below describes them. Nothing in them changed after function values went through the IR ([[MYLA-106]]); making it the only path, and every optimisation since, needed only the lowering or the backend. The additions since are the `become` terminator (D87, [[MYLA-128]]), made as the first rule below says, and a parameter slot that holds an aggregate by value (`inline`, D88, [[MYLA-131]]): its argument words hold the aggregate, read through `addr $slot`, where an aggregate parameter's slot otherwise holds its address, read with `load`. Then async functions' frame functions (D90, [[MYLA-138]]): a function marked `frame` (`fun myla_f -> int32 frame {`) keeps every slot in its heap frame instead of the stack frame, which is the backend's business (instructions reach slots only through `$s`); the `%t = frame` instruction gives the frame's address, and the `suspend L` terminator leaves the function to resume at `L`. And `deep T [%p]` (D92, [[MYLA-137]]): every heap value the T at `%p` owns replaced by a deep copy of its own and the original released, an actor handle staying shared; the verifier treats it as it treats `retain` (no slot changes hands). And `clone T [%p]` ([[MYLA-148]]): the T at `%p`, a word-for-word copy of a value others hold, made a deep copy of its own, the original only read (its counts untouched; an actor handle retained atomically), for a child reading a sibling's result while the parent may read it too.

- **Adding an instruction** means, in one change: its entry below and its text form (`render_inst`), the verifier's rule when it touches an owning slot, and its code in every backend.
- **Changing what an instruction means, or removing one**, needs a new decision.
- **Free to change:** which instructions the lowering emits for a construct, and how a backend carries them out (instruction selection, registers, the frame layout), as long as the verifier accepts every function and the gates pass.
- **Outside the IR,** for each backend to provide: the runtime (hand-written x86-64 assembly called with the System V argument registers), the per-type retain, drop and clone walks behind `retain`, `drop` and `cow`, and the thunks and environment release functions of function values. How an LLVM backend gets them is [[MYLA-62]]'s decision.
- **Known pressure points,** each a decision of its own when it comes:
  - *One class of temporaries:* every temporary is an 8-byte value in a general-purpose register. Floats already pay for it (moved to `%xmm0`/`%xmm1` for every operation, `emit_float_op`). SIMD vectors or 128-bit integers in temporaries would need wider temporaries and loads, stores and constants with a width, register classes, a caller-saved allocator (no `%xmm` register survives a call under System V), slot alignment and a calling convention for them. As aggregates in slots, with new instructions, they would fit today's rules, but slowly.
  - *Untyped addresses:* an address is a `uint64` temporary. x86 doesn't care; LLVM's provenance and alias analysis want a pointer type, and so would references in the language. Best settled with [[MYLA-62]].
  - *Calls never end a block:* nothing leaves a function between two instructions (a `panic` aborts, `?` is an ordinary branch). Running drops while a `panic` unwinds, or catchable errors, would need calls that end a block with an unwind successor (LLVM's `invoke`) and cleanup blocks the verifier follows on every exit.
  - *Slots live in the frame* (settled by D90 for async functions: a frame function's slots are all in its heap frame; the rest of this point is how it stood): a suspended coroutine must keep its slots between resumes. Stackless coroutines (C#'s and Python's state machines, Swift's async functions; the scheduler, an event loop or a task executor, doesn't matter here) need them in a heap frame: either a lowering that turns them into members of a heap object (today's instructions suffice, but the verifier and the allocator no longer see them as slots) or a new home for slots. Swift's split functions also need guaranteed tail calls, which `become` now provides (D87; the callee pops its arguments, [[MYLA-126]], so a jump to a function with more arguments reuses the frame too). Stackful coroutines (Go, Lua) need nothing from the IR, only stack switching in the runtime.
  - *One thread:* `retain` is a plain `incq` and `cow` trusts a count of 1. Values shared between threads would need atomic counts (a variant of `retain`, so the rest stays cheap) or a type that keeps them from being counted.
  - *Lowered per target:* sizes, field offsets, element sizes and the cell layout `elem`, `append` and `pop` assume (length at 0, capacity at 8, elements from 16) are constants in the IR. A target with other sizes (32-bit wasm) means lowering again for it; a calling convention (Windows x64) is the backend's.
  - *Monomorphic* (decision 3): `copy` has a constant size and `retain` and `drop` a static type. Code shared between a generic function's instances would need sizes and walks from runtime type descriptors.

  References would otherwise need little new in the instruction set (`&x` is `addr $x`; `var self` already is a mutable reference). What they would break is in the language and the lowering: [[MYLA-122]]'s borrowing relies on `let`s being deeply immutable, [[MYLA-123]] on aliasing only through a `var self` receiver, and a pointer into a list dangles when the list grows or is copied on write.

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
%t = frame                    ; a frame function's heap frame (D90)
deep T [%p]                   ; the heap values of the T at %p copied deeply,
                              ; the originals released (D92)
clone T [%p]                  ; a copy of a value others hold made a deep copy,
                              ; the original only read (MYLA-148)
```

*Now*: `const`, `str`, `load`/`store` of 8-byte slots, `addr` (a slot's address), `%t = %p + off`, `load`/`store` at `[%p + off]`, `copy size [%dst], [%src]`, `call … sret %r` (an aggregate result into the storage at `%r`), `rt name(%args)` (a runtime helper such as `__str_concat`, the arguments in `%rdi`, `%rsi`, …), `retain T %v` (a cell) and `retain T [%p]` (every heap value of the T at `%p`), `drop T $slot` (an owner's end) and `drop T [%p]` (a member before it is overwritten), `init $slot` (an aggregate built member by member is complete; no code), `elem %cell[%i] stride` (an element's or byte's address, bounds-checked at a position), `load8`, `cow T [%holder]` (the cell made unique, a clone stored back when shared), `append [%holder] %cell stride` (room for one more element, the grown cell stored back), `pop %cell stride` (the last element's address, trapping when empty), `%t, %t2 = rt name(%args)` (a helper returning `%rax` and `%rdx`: `__map_set_slot`'s slot and whether the key was there), `check %v kind` (trap when `%v` is 0: a missing map key), `sbappend`/`sbappendbyte`/`sbbuild` (the builder sequences), `mapremove T [%holder] %cell %key`, `global sym width` (a runtime variable such as `__io_errno_val`), `exit %code`, `moved $slot` (an owning slot's value was moved into a container; no code, for the verifier), `label sym` (a code address), `call [%fv](%args)` and `call [%fv](%args) sret %r` (through a function value: its environment the word after the result's address), the integer and float operations (`%t = + int32 %a, %b`, with the result type after `->` when it differs, and `@line:col` on a division), `cmp`, the unary operators, `cast`, `call` with scalar arguments, `print ty %a` (a scalar, as `print` writes it), `loc`, `bind`, and `scope open`/`scope close` (the lexical scopes of debug information, which `emit_ir` turns into the same DWARF blocks as the old path).

Terminators (*now*: `jmp`, `br`, `ret`, `become`, `suspend`, `trap`, `panic`):

```text
jmp L3
br %c, L4, L5
ret                           ret %t
become                        ; the call before it runs in place of the function (D87)
suspend L6                    ; a frame function records L6 as where it resumes and leaves:
                              ; the call before it, if any, runs in place of it, else back
                              ; to the executor (D90)
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

### Optimisations

[[MYLA-108]], each measured on the compiler compiling itself (the table is on the task):

- **Walks out of line.** An enum's retain or release walk, or that of a struct or tuple with several owning members, is a helper (`__walkd_T`, `__walkr_T`) instead of a tag dispatch at every site.
- **Temporaries in `%rax`.** A temporary read by the next instruction is taken from `%rax`; its store is written only if something else reads it (`use_counts`).
- **Recomputed, not stored.** A temporary written once by a constant, a string's, symbol's or slot's address, or read from a variable that nothing writes before its reads (in its block), is recomputed where it is read (`remat_texts`; `def_counts` keeps those written in several blocks, like `&&` results).
- **Moves.** A new value (a call's result, a literal, a concatenation) bound for a place is moved out of its temporary instead of retained and then dropped (`take`, `holder`).
- **In place.** `let` and `return` offer their destination to the aggregate they evaluate: literals and direct calls build their value there (`into`, `placed`).
- **Reachable functions only.** The worklist starts at the entry point; each function queues what it calls, makes values of or applies partially.
- **Shared frame cells.** Temporaries living in one block share cells by a linear scan, next to `%rbp`; those living in several blocks keep their own.

[[MYLA-120]], instruction selection (the IR is unchanged):

- **Compare and branch.** An integer comparison whose only use is the branch ending its block is a `cmpq` and a conditional jump; a branch falls through to whichever successor comes next.
- **Operands where they are.** The second operand of `+ - * & | ^` and the comparisons is an immediate, the variable's slot a temporary was read from, or the temporary's cell, instead of being loaded into `%rcx`.
- **Addressing modes.** Loads and stores through a slot's address use the frame directly; an element's address is one `leaq` and folds into the load after it; 32-bit constants load with `movq`; integers wrap to their width in one instruction.
- **Unreachable blocks** get no code, only their debug scopes.

The compiler's binary got 11% smaller and runs 12% fewer instructions compiling itself ([[MYLA-120]] has the measurements).

[[MYLA-121]], register allocation:

- **Callee-saved registers.** Temporaries that would need a frame cell and scalar slots that only `load` and `store` touch (parameters included) live in `%rbx` and `%r12`–`%r15`: one live interval each over the reachable blocks in emission order (liveness across blocks by a backward dataflow, `live_spans`), handed out by a linear scan in which the value with fewer loop-weighted reads and writes gives way (`alloc_regs`). A function saves the registers it uses in the prologue, only when their values weigh enough (`REG_MIN_USE`), and not under `-g`.
- **Registers read directly.** Loads and stores through a pointer in a register, offsets, reference counts, tests and compare-and-branch use the register; stores take an immediate or a register as their source; a commutative operation or a comparison takes a second operand still in `%rax` first.

The compiler's binary got 7% smaller and compiles itself about 3–4% faster; the stress programs 2.6% faster overall, lists 25% ([[MYLA-121]] has the measurements).

[[MYLA-122]], borrowing: a `let` of a part of a fixed variable, and a `for` over one, take no reference (see "Lowering ownership" below); 1.4% fewer instructions compiling itself. Such a slot owns nothing, so a scalar one can live in a register too.

[[MYLA-125]]: a division by a constant other than 0 and −1 tests nothing (an unsigned power of two is a shift or a mask), a negative integer literal is a constant, and a value loaded for a register goes straight into it (the held-back move folds into the load); 2% fewer instructions compiling itself.

[[MYLA-126]], tail calls: a direct call whose result is returned at once, with no argument pointing into the frame, jumps (not under `-g`). Every function pops the argument words its caller pushed (`ret $8n`, `ret_popping`), so the callee's arguments go to the top of the caller's words and the return address right below them, whatever the two counts; the owners dropped after the call go before the jump when nothing it passes depends on them (`drops_after_free`). With owned parameters ([[MYLA-127]]) a recursion threading a list or string runs in constant stack. The adapter from the closure convention to a plain function and `__compose_call` jump too, and so do partial applications' thunks ([[MYLA-130]]).

[[MYLA-128]], guaranteed tail calls (D87): `become f(args)` lowers to the arguments, the drops of every owner and temporary, the call (`call`, `call … sret` with the function's own result address, or either through a function value) and the `become` terminator; the backend always emits that call as the jump above (`emit_tail_call`, `emit_frame_handover`), under `-g` too, through a function value with its code in `%rcx`. The checker allows only arguments that need nothing from the frame, and records the parameters a `become` hands a heap value over to (`handovers`), which `find_kept_params` makes owned, and those it passes on to a function value, which stay borrowed.

[[MYLA-130]]: a word a tail call passes on in the place it came in (a parameter passed in its own position, the result's address) stays there instead of being pushed and popped; `moves` also hands over a slot read (only read: `only_reads`) between the retain and the drop while the retained value isn't taken yet (its taker would share the value at one reference less and could change it in place), keeping plain scalars read out of it out of the family, so a `become` passing on a list it also indexes no longer retains and releases it; and a partial application's thunk jumps to its function. A recursion over a list through `become` runs 6% fewer instructions; compiling itself costs 0.02% more (the longer scan) and its code is 1.6 kB smaller.

[[MYLA-133]], hot spots of the self-compile: `__str_eq` compares eight bytes at a time; `__map_hash` multiplies a value key by 2^64/φ instead of eight FNV-1a rounds, and mixes a string in eight bytes at a time; the lexer keeps the list `chars` decodes instead of copying it, and appends an ASCII lexeme's bytes without a string per character; `==` on an enum without payloads whose `eq` is derived compares the tags inline (`tag_only_eq`) instead of calling the routine. Together 9.2% fewer instructions, but only 1–2% less wall time: the self-compile is bound by memory traffic (65% of its instructions read or write memory, mostly the generated code's frame cells), not by instructions. Copying list cells eight bytes at a time instead of `rep movsb` saved 3.5% of callgrind's count, which counts that instruction per byte, and no wall time, so it was left out.

[[MYLA-134]]: the allocator also hands out %r8-%r11, which need no save, to a value whose interval contains no position that calls something or uses them (`clobbers`): a compute-bound program runs 11% faster (the same instructions, the frame's loads and stores turned into register moves), and compiling itself executes 19% fewer frame loads and 40% fewer frame stores, with its time unchanged. %rsi and %rdi as well paid nothing.

Altogether the self-compile went from 3.80 s (the old path) to about 1.9 s, the binary from 2.39 to 1.39 MB, and the peak from 128 to 89 MB; with the lookup tables of [[MYLA-119]], the work above and fewer copies in the compiler's own code ([[MYLA-124]]) it takes about 0.8 s (median of alternating runs), its binary is 1.24 MB and its peak 92 MB. Callee-saved registers for the four most-used scalar locals were tried and didn't pay off; the register allocator over temporaries and locals of [[MYLA-121]] does. [[MYLA-122]] leaves out the retain/release pair of a copy of a fixed variable. The linear lookups that took most of the remaining time are gone ([[MYLA-119]]), and so are the biggest copies the compiler's own code made ([[MYLA-124]]).

### Lowering ownership

[[MYLA-105]] lowers strings, and aggregates holding them, with every rule of [[Architecture/Native-backend#heap-and-reference-counting]] as an instruction:

- **Owners.** A local owns its value: binding it copies and retains (`retain`). It is registered with its scope, whose end drops it (`drop $slot`), and `return`, `break` and `continue` drop the owners of the scopes they leave.
- **Temporaries.** An owned temporary (a call's result, a concatenation, an aggregate literal holding a string, a `match`'s value) lives in an owning slot registered with the statement, which drops it at its end. Where no statement end follows, it is dropped right after the value is known: a condition, a guard, an operand of `&&`/`||`, a range bound, an arm's expression. `return`, `break` and `continue` also drop the temporaries of the statements they leave.
- **Borrowing.** Parameters borrow unless they are owned (below), and match bindings borrow; nothing drops them. So does a `let` of a part (the whole, a field, a tuple's or a list's or map's element) of a *fixed* variable: a `let`, a parameter other than `var self`, a capture or a `for` loop's element. Nothing writes either while the `let` lives, and the variable, being in scope, outlives it, so its copy takes no reference and its slot owns nothing ([[MYLA-122]]). A `for` loop over a fixed variable likewise needs no reference of its own.
- **Assignments.** An assignment takes the new value (retains it, staged in a slot of its own for an aggregate) before it releases the old one (`drop $slot` for a local, `drop [%p]` for a member), which the new value may share (`p = p`, `o.a = o.a`).
- **Parameters passed by value** (D88, [[MYLA-131]]). A struct, tuple or enum parameter that a `become` hands one over to holds it in its argument words (an `inline` slot, as many words as the value has), owning what it holds and dropped as a local is. A caller copies the value's words into its argument words with references of their own (`value_words`: taken from an owned temporary, else retained); so do the adapter from the closure convention and partial applications' thunks (`push_value_words`), and an operator's `eq` or `cmp` call.
- **Owned parameters** (D86, [[MYLA-127]]). A parameter that is a string, list, map or builder, which the function keeps as a whole value and whose calls mostly pass it a new value, or which a `become` hands a value over to (D87), is owned: an owning slot that holds a value on entry (the verifier knows), registered with the function's scope, so every exit drops it unless it is moved on. A caller hands over an owned temporary (`take`) or retains; calls through function values keep borrowed parameters, and the adapters retain. `find_kept_params` decides, from one scan over every body (`scan_*`) before anything is lowered: what each body keeps, and what each call passes.
- **Moves** ([[MYLA-127]]). After lowering, `moves` hands an owning slot's reference over at its last use: in a block, a `retain` of the whole value the slot holds (loaded, or copied out of its address) followed by the slot's `drop`, with nothing reading the slot or anything taken from it in between (the retained value read once, by whoever takes it), loses the retain, and the drop becomes `moved`. A slot something that owns nothing holds a part of (a borrowing `let`, a loop's list, a match's borrowed copy: `borrowed_slots`) keeps its reference, as the borrower may still read the value. Returning a list or struct built in a local, or passing it on owned, no longer retains and drops it.
- **Arguments.** Arguments are passed as they are, borrowed, or owned as above. A method that writes its receiver (`var self`) gets a staged copy of an argument read from the receiver's variable instead (`b.rename(b.name)`, `w.move(w.p)`: an aggregate or a value owning heap memory), as the interpreter passes copies ([[MYLA-123]], [[MYLA-129]]); its writes would change or release the argument's place otherwise.
- **Staged values.** A value bound for a container or a member (`xs[i] = v`, `m[k] = v`, `push(xs, v)`, `o.f = v`) is taken first, as the interpreter does (MYLA-4), into an owning slot registered with the statement; the place, the index or the key evaluated after it may still leave the function (`m[f()?] = v`), and then the statement's drops release it. Once it is stored, `moved $slot` hands its references over and the slot leaves the statement's temporaries.
- **`?`.** On success the payload is borrowed from the operand. On failure, the tag and the failure's payload (not the whole operand, MYLA-80) are copied into the result's storage and retained; the temporaries and owners are then dropped as for `return`.
- **Function values.** A function value is 16 bytes, its code and its environment (a cell whose first word is its release function, or null), retained and released through the environment as on the old path. A lambda copies its captures into a new environment with references of their own (D48), and its body (`lower_lambda`) copies them out into slots of its own at entry, borrowed as parameters are; a partial application evaluates its receiver, filled arguments and called function value into one; `>>` puts both function values into one for the runtime's `__compose_call`; a named function becomes its thunk with a null environment. The value is the statement's until it is stored. A call through one evaluates the callee first, then the arguments.
- **Destructuring.** Each name of `let (a, (b, _)) = …` is a variable of its own, holding a retained copy of its element.
- **Lists.** A list literal is a new cell, its elements stored with their own references, owned by the statement. Reading an element borrows it from the list (bounds-checked, `elem`). A write to an element (`xs[i] = v`, `xs[i].f = v`, at any depth) takes the value first, then makes every list on the path to the place unique (`cow`), as the old path's `mut_place_addr` does, then releases the old element. `push` takes the value, makes the list unique, grows it when full (`append`) and moves the value in; `pop` moves the last element out to the statement. A `for` loop over a list holds a reference of its own for the loop (dropped at its end, or by a `return` from the body; not for a fixed variable, see Borrowing) and borrows each element.
- **Maps.** A map literal is a new map owned by the statement, each key evaluated before its value. A read (`m[k]`, also inside `get`) borrows the value, trapping when the key is missing (`check … key`). `m[k] = v` takes the value first, makes the map unique, finds or makes the key's slot (`__map_set_slot`, which retains a string key), releases the value it held when the key was there, and moves the new one in; a write into a value (`m[k].f = v`, `push(m[k], x)`) makes the map unique and traps on a missing key, as the old path's `mut_map_value_addr`. `remove` makes the map unique and releases the key and value (`mapremove`); `keys`, and a `for` loop over a map, make a new list of the keys.
- **Recursive enums.** A recursive enum's value is inline in a variable, a parameter, a result and a match's copy, but a member (a field, payload, tuple, list element or map value) holds a pointer to a box, as on the old path. Reading such a member as an aggregate borrows the box's value (`unbox`, also in sub-patterns, which match against the box). Storing one makes a new box holding a retained copy (`box`, the old path's `box_value`); assigning it to a member releases the old box (`drop [%p]`), and `pop` copies the value out with references of its own before releasing the box.
- **Builders and `format`.** `StringBuilder()` is a new cell; `append` and `append_byte` make it unique first. `build`, `chars`, `format` (and so f-strings) and every rendered piece make new strings owned by the statement; unlike the old path, which releases each piece as soon as it is concatenated, the IR keeps them until the statement ends.
- **The I/O intrinsics.** Runtime helpers (`rt`) or runtime variables (`global`); a cell they return is a new reference (`__run_stderr` hands over the runtime's).
- **Matches.** A match copies its scrutinee; the copy owns references of its own (retained, dropped after the match or by an arm's early exit) only when an arm may write the variable the scrutinee came from (MYLA-2).

The **verifier** (`verify` in [[selfhost/ir.my]]) follows every owning slot along the reachable paths. It rejects a store into a slot that still holds a value, a drop of one that holds none, a slot holding a value at `ret` or `become`, a `become` after anything but a call, and paths that join disagreeing on a slot. It treats `suspend L` as `jmp L`: a frame function's owning slots stay owned while it is suspended, since they live in its heap frame. A `copy`, `call … sret` or `init` into an owning slot stores into it. A function it rejects falls back to the old path with the reason `IR verifier: …`, which the IR gate treats as a failure.

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
| [[MYLA-120]] | Instruction selection: compare and branch, operands where they are, addressing modes, no code for unreachable blocks |
| [[MYLA-121]] | Register allocation: liveness across blocks, a linear scan over the callee-saved registers |
| [[MYLA-122]] | Borrowing: a `let` of a part of a fixed variable takes no reference |
| [[MYLA-109]] | The IR declared stable (D85); an LLVM backend on it is [[MYLA-62]], an IR interpreter waits until bugs call for one |
