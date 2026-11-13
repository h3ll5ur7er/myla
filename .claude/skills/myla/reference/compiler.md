# The compiler: architecture, back end, and how to add a feature

Written from the code at 706eaec (2026-11-13). Function names are real; line counts are `wc -l`. Where the wiki disagrees, the code is right (the stale points found are in [[MYLA-582]]).

## Pipeline

```
source .my
 └─ lexer.my      lex(src) / Lexer.run → [Token]         f-strings become tokens `format("…{:spec}…", holes)` here
 └─ parser.my     Parser.parse_program → Program{decls}   (statement / assign_or_expr / pipe→logic_or→…→unary→postfix→primary)
                  desugars: |> , return a,b , if-as-value, if let / while let / let-else, a op= b, slices, ^n
 └─ loader.my     load_program_opts(entry, LoadOptions) → Loaded{decls, next_id, spans, std_impls, bodies}
                  imports depth-first, names qualified `mod$name`, implicit std modules merged first,
                  std bodies left unparsed (D179) or read from astcache (embedded parse); runtime=true adds std/rt.my
 └─ checker.my    build_checker_lazy(decls, next_id, primitives, std_impls, bodies) → Checker
                  prelude_src() (Option, Result, Format, Hasher, Hash, Iterator) prepended; run_all;
                  output = side tables keyed by node id: resolved[id] = Type, static_calls, impl_args, …
                  and fill_in: bodies rewritten in place (same ids) for calls with default arguments,
                  `for x in iterator` as a while-let loop, renamed callees (Fills, fd_stmt/fd_expr)
 ├─ interp.my     new_interp(checker, argv).run() / run_tests()     — myla run / test / repl
 │                (async bodies normalized by anf.my, run on an async evaluator)
 └─ codegen.my    new_codegen(checker); g.generate()                — myla build, gen_main
     per function (worklist from the entry point, monomorphized on demand: request_fn / mangle_fn):
       gen_any_function / gen_any_lambda
         anf Norm.block            (only async fns when the program has tasks: g.frames)
         lower.lower_function / lower_lambda → Lowered{f: IrFunc, lams, partials, fnvals, refused, wants}
       take_ir:  ir.moves → inline.inline_small+merge_blocks → hoist.hoist_cows → ranges.widen_counters → ir.verify
                 (queues instances, called fns, lambdas, partials, fn values, per-type routines)
       emit_ir_at (ir_x86.my):  ssa.promote (--ssa only) → hoist_tail_drops → ownership.expand_ownership
                 → emit_wasm (ir_wasm) | emit_a64 (ir_a64) | x86 selection + register allocation (ir_x86)
     then partials, fn-value thunks, drop helpers; assemble_source() (x86/a64 text) or wasm_module()
 └─ driver.my     build_commands: as+ld (x86-64), clang+ld.lld (aarch64), clang+wasm-ld (wasm32)
```

Entry points: `main.my` (CLI) → `driver.my` (`cmd_interp`, `cmd_test`, `cmd_test_native`, `cmd_build`, `load_and_check`, `compile_asm`). `gen_main.my` is the bootstrap compiler: `build/stage3 file.my lib [-g] [--emit-ir] [--ssa|--ssa-stats] [--no-inline] [--checked] [--primitives] [--async-frames] [--target t] [--package n=dir] [--root d] > out.s`. `myla build` has none of the debugging flags (`--emit-ir` etc.); use `build/stage3` (or `build/gen_tool`) for them.

## Files of selfhost/ (46)

| File | Lines | Role |
| --- | ---: | --- |
| `tokens.my` | 260 | `TokenKind`, `Token`, `SrcSpan`, `Diag`, `Note`; `keywords()` (pinned, see checklist), `keyword_kind` |
| `lexer.my` | 1424 | Source → tokens (code points; columns as Python's); f-strings → `format(…)` tokens; `#test` attributes skipped unlexed in lazy mode; first error only |
| `unicode.my` | 64 | XID_Start/XID_Continue ranges (generated) |
| `util.my` | 172 | UTF-8, escaping, char classes, `format_specs`, `written_type_name` |
| `ast.my` | 693 | AST node structs/enums, `dump_*` canonical S-expressions, `names_in_expr/block`, `bind_elems`, unread-body markers |
| `parser.my` | 3013 | Recursive descent, error recovery (`recovered`, `sync`, MAX_ERRORS), all syntactic desugarings; `expr_of`/`stmt_of`/`block_of`/`fun_of`/… for `#test` cases; `parse_source*` |
| `loader.my` | 2137 | Module graph, qualification (`Renamer`), exports, implicit modules, per-target platform file (`for_target`), lazy bodies |
| `astcache.my` | 1605 | Text encoding of a std module's parse (`Writer`/`Reader`, `cache_entry`, `decode`), stored in embedded_std.my (MYLA-412) |
| `stdroot.my` | 96 | `EMBEDDED_ROOT = "<myla>"`, `default_stdlib_root` (MYLA_STDLIB), embedded file lookup |
| `embedded_std.my` | (2.3 MB) | GENERATED: every `lib/` file's text + each std module's parse; never edit |
| `checker.my` | 12472 | `Type`, `CheckErr`, prelude, name tables, inference (`infer_node`, `infer_call`, …), `check_stmt`, traits/generics/derives, exhaustiveness, const folding, actor analyses (`Effects`, `Reads`, `Reentrancy`), builtin & primitive tables |
| `diag.my` | 246 | `Report`, `render` (carets), `canonical` |
| `interp.my` | 7199 | Tree-walking interpreter: `Value`, `Interp.eval`/`exec_stmt`, places, tasks/actors scheduler, `run_tests`, `session_step` |
| `anf.my` | 627 | `Norm`: async bodies with each `await` in `let t = await x` (interpreter's async evaluator and the compiler's frame functions) |
| `codegen.my` | 5152 | `CodeGen` state (checker tables copied, layouts `size`/`field_offset`/`variant_tag`, string/position pools, worklists), monomorphizer (`generate`, `request_fn`, `solve_targs`), `take_ir`, x86 text assembly (`assemble_source`, data/runtime variables), DWARF (`dbg_*`), shared x86 instruction helpers (`emit_int_op`, `emit_cast`, …), many predicates (`is_aggregate`, `is_cell_t`, `type_key`, `mangle_fn`, `is_builtin_call_name`, `trap_labels`, `tls_offset`) |
| `lower.my` | 8083 | Checked AST → `IrFunc` (`Lower` methods `stmt_body`, `expr`, `addr`, `call`, `direct_call`, `match_expr`, `pattern`, …); every per-type routine as IR (`derived_eq_ir`, `key_hash_ir`, `map_*_ir`, `walk_ir`, `clone_ir`, `deep_*_ir`, `env_*_ir`, `partial_ir`, `frame_new_ir`, `compose_ir`, `trap_value_ir`); `myla_runtime_function` |
| `ir.my` | 1556 | IR types (`Inst`, `Term`, `Intrinsic`, `Slot`, `IrFunc`), text form (`render_func`), ownership verifier (`verify`), `moves` (last use moves), use/def helpers |
| `ir_util.my` | 60 | Backend helpers: `reachable_blocks`, `wrapped`, `int_in`, type tests |
| `inline.my` | 433 | Small scalar leaf functions of the same module copied into callers (`inlinable`, `inline_calls`, `merge_blocks`) |
| `hoist.my` | 397 | A loop's list copy-on-write check made once before it (`hoist_cows`, MYLA-251) |
| `ranges.my` | 311 | Counter `+ 1` proven not to overflow retyped int64 (`widen_counters`, MYLA-251) |
| `ssa.my` | 604 | D123 prototype: scalar slots promoted (Braun et al.), back to temps+movs; only with `--ssa` |
| `ownership.my` | 209 | `expand_ownership`: retain/drop/cow/deep/clone → loads, `intr rc_inc/rc_dec`, calls of per-type routines |
| `ir_x86.my` | 3936 | `impl CodeGen`: `emit_ir`/`emit_ir_at`, instruction selection, register allocation on live intervals, frame layout (`slots_at`, `frame_size`, `tail_call_at`, shared by the other backends) |
| `ir_a64.my` | 1231 | `impl CodeGen`: `emit_a64`, every temp in a frame cell; `emit_fnval_thunk_a64` |
| `ir_wasm.my` | 1499 | `impl CodeGen`: `emit_wasm`, LLVM wasm asm, locals, `br_table` dispatch loop, shadow stack |
| `runtime_x86.my` | 608 | `emit_runtime_prelude`: `_start`, traps/`__panic`, `__syscall*`, `__copy_bytes`, workers, frame jumps, `__fmod` |
| `runtime_a64.my` | 500 | `emit_runtime_prelude_a64`: same for aarch64 |
| `runtime_wasm.my` | 485 | `emit_runtime_prelude_wasm`, WASI dispatcher, `wasm_module` (aliases resolved, types declared, data sized) |
| `dwarf.my` | 248 | LEB128, abbreviation table, `read_gdb_script` (for `-g`, x86-64 only) |
| `driver.my` | 600 | Command implementations; native test harness runs; assembler/linker invocation |
| `main.my` | 234 | CLI argument parsing and dispatch |
| `repl.my` | 591 | `myla repl` |
| `harness.my` | 776 | The program `myla test --native` builds (a function per case, structural eq and repr per type) |
| `test_programs.my` | 208 | `// input:/output:/exit:/stderr:` blocks of a project's test programs |
| `project.my`, `project_cmd.my`, `fetch.my` | 1040/457/242 | Project tool (`myla.toml`, lock, commands, Git deps) |
| `play_main.my` | 125 | Checker+interpreter for the wasm web page |
| `gen_main.my` | 140 | Bootstrap compiler entry (above) |
| `lex_main`, `parse_main`, `check_main`, `interp_main`, `floatlit_main`, `project_main` | 17–191 | Drivers for the differential burn tests |

Not in selfhost but part of the compiler: `lib/std/rt.my` (5464, the runtime in Myla), `lib/std/platform.my` / `platform_aarch64.my` / `platform_wasm.my` (system-call layer per target, `TARGET` const), `lib/std/fmt.my`, `slice.my`, `num.my` (called by name from the lowering), `tools/embed/main.my` (writes embedded_std.my), `tools/grammar/` (EBNF → tree-sitter), `tools/lsp/` (language server: `resolve.my` walks the AST, `features.my` completion keywords).

Module cycles are allowed: `lower` imports `codegen` and `codegen` imports `lower`; `ir_x86`, `ir_a64`, `ir_wasm`, `runtime_*` add `impl CodeGen` blocks from other modules.

## Data structures

**AST** (`ast.my`): every node is a wrapper `{id: int32, line, col, sp: SrcSpan, kind}`; `id` is unique across the program (parser `fresh()`, threaded through modules by the loader), and keys every side table.

- `ExprKind` (21): `IntLit(v, suffix, is_char, big)`, `FloatLit(lexeme, suffix)`, `StrLit`, `BoolLit`, `Name`, `Unary(op, x)`, `Binary(op, l, r)`, `Call(callee, args, targs)`, `GetField`, `StructLit`, `TupleLit`, `TupleIndex`, `ListLit`, `MapLit`, `Index`, `MatchE(scrut, arms)`, `Try`, `Cast`, `Lambda(params, ret, body, async)`, `Await`, `Hole`.
- `StmtKind` (11): `VarDecl(kind "let"/"var"/"async", name, ty, init)`, `DestructDecl`, `Assign(target, value)`, `IfS(c, then, Option<ElseTail>)`, `WhileS`, `ForS(var, start, end, body, iter)`, `ReturnS(value, is_become)`, `BreakS`, `ContinueS`, `ExprStmt`, `DeferS(Block)`.
- `PatternKind`: `PWild`, `PBind`, `PLit`, `PEnum(enum?, variant, elems, has_payload)`, `PTuple`, `PStruct`, `POr`. `TypeKind`: `TRef(name, args)`, `TTuple`, `TList`, `TMap`, `TFn(params, ret, async)`. `DeclKind`: `StructDecl` (actor flag), `FunDecl(FunData)`, `EnumDecl`, `TypeAliasDecl`, `ImplDecl`, `TraitDecl`, `ConstDecl`, `ImportDecl`.
- Forms with no node of their own (the parser builds them from existing nodes, so every walker already covers them): `if c {a} else {b}` as a value = `MatchE(c, [true => a, %else => b])`; `if let`/`while let`/let-else = `MatchE` whose second arm binds `%iflet`/`%whilelet`/`%letelse` (checker `if_worded` rewrites messages); `a op= b` = `Assign(p, Binary(op, p, b))`, with non-trivial indices hoisted into `let %index<id>` inside `if true { … }` (`compound_assign`, `hoisted`; `fused_compound` lets both runners find the place once, MYLA-506); `xs[^n]` = `Index(xs, Unary("^", n))`; `xs[a:b:s]` = `Index(xs, Binary(":", Binary(":", a, b), s))`, a missing bound `Hole` (`is_slice_expr`, `slice_parts` in checker); `x |> f(y)` = `Call(f, [x, y])`; `return a, b` = tuple; f-strings = `format` call (lexer). Generated names start with `%` (`%else`, `%index12`, `%aw3`, `%for12`), which no program can spell.

**Checker** (`checker.my`): `Type` = `TInt(width, signed) | TFloat(w) | TChar | TBool | TStr | TSB | TStruct(name, args) | TEnum | TTuple | TList | TMap | TFunc(params, Option<ret>) | TAsync(TFunc) | TActor | TParam | TSelf | TError | TPtr` (TPtr: IR only). `Checker.resolved: [int32: Type]` (every expression's type), `FuncSig` (with `decl: FunData`), `StructInfo`, `EnumInfo`, `TraitInfo`, `MethodEntry`, `Subst{name, ty}`, `subst_type`. No separate typed AST: the back ends read the AST (as `fill_in` left it) plus `resolved` (`CodeGen.type_of(id)` applies the current monomorphization `subst`).

**Operators by type arguments** (D200, [[MYLA-612]]): the checker keeps `op_impls: [OpImpl]` (trait, target key and type, right operand `r` or `r_self`, result `o`, the renamed method `Key.mul$float64`), filled in `resolve_impl` (`op_impl_kind`, `rename_impl_methods` renames in `decls` too, as the interpreter and harness collect methods from there). It records each operator that calls one in `op_sites[node id]` (`Binary`, `Unary` `-`, `Index`; `IndexSet` targets in `op_sets`, since a compound assignment's target node is also its value's left operand): the method (`mul$float64`), or `""` in generic code, where the runner picks by the concrete types (`find_op_impl`). No AST node is added: the interpreter (`op_call` → `eval_method_call(e, l, m, [r])`) and the lowering (`Lower.op_call`/`CodeGen.op_method` → `direct_call(cg, e, m, [l, r], into, false)`) call the method where the operator stands, so `anf`, `fill_in` and the other walkers are untouched. A pattern to reuse: a feature that is a method call in disguise needs a checker side table and a branch in each runner, not a new node.

**IR** (`ir.my`; text form via `--emit-ir`): `IrFunc{name, ret, slots: [Slot], temps: [Type], blocks: [IrBlock{insts, term}], order, instances, frame, scope_parent}`. Temps are 8-byte scalars (not SSA); slots are frame memory (`Slot{name, ty, size, word (argument index, ENV_WORD=-2, -1), owns, inline, scope}`).
- `Inst` groups: constants/addresses `Const, Str, Addr, Offset, Label, Global, Frame`; memory `Load, Store, LoadAt, StoreAt (width), Load8, Copy, Mov`; arithmetic `Bin (traps at Pos on /0), Cmp, Un, Cast`; calls `Call, CallSret, CallInd, CallIndSret, Rt (named runtime routine), Intr (Intrinsic)`; ownership `RetainVal, Retain, DropSlot, DropVal, DropAt, Deep, CloneDeep, Init, Moved, Cow`; containers `Elem (bounds-checked or not), Append, Pop, Check (trap kind), SbAppend, SbAppendRange, SbAppendByte, SbBuild`; misc `Print, Exit, Loc, Bind, Scope`.
- `Term`: `Open, Jmp, Br, Ret, Become, Trap(kind, Pos), Panic(msg, Pos), Suspend(resume block)`.
- `Intrinsic`: `Sqrt, F64Round, F64Bits, F64FromBits, Rotl, Bsr64, Cas64, Xchg64, FetchAdd64, LoadAcq64, StoreRel64, Pause, RcInc(Atomic), RcDec(Atomic), Unique(clone), RtAddr(sym), RtWaddr(sym), RunFrame, CallCode, Fits(op, signed)`; `primitive_intrinsic(name)` maps `__cas64` etc.; each backend implements every one (contract: docs/Architecture/IR.md "What each instruction means").

**Names in the output**: free function `mod$name` (`std$rt$alloc`, entry module unqualified: `main`); method `TypeKey.method` (`str.split`, `__list.first`, `__map.get`, `Point.shifted`; `CodeGen.type_key`); generic instance `mangle_fn(name, targs)`; assembly symbol `myla_<name>`; per-type routines `__drop_list_<T>`, `__walkd_<T>`, `__clone_…`; traps `__trap_<kind>`.

## The runtime, in three layers

1. **Hand-written per target** (`runtime_x86/a64/wasm.my`, emitted as text by `emit_runtime_prelude*`): `_start`, `__panic` and the `__trap_*` entries, `__syscall`/`__syscall5`, `__copy_bytes`, threads/workers, frame jumps; plus the data labels of the **runtime variables** (`__exit_hook`, `__panic_buf`, `__heap_ptr`, … emitted in `assemble_source`/the preludes; per-worker ones live in the thread block at `tls_offset(sym)`). IR reaches them by `Inst.Global(sym)` and `Intr RtAddr/RtWaddr(sym)`; std.rt by `__rt_get("sym")`, `__rt_addr("sym")`, `__rt_waddr("sym", w)` (lowered in `Lower.io_call`).
2. **std.rt in Myla** (`lib/std/rt.my` over `std.platform`, raw memory through `__load64`/`__store64`/`__alloc`/`__addr_of`/`__str_of`/…, `is_raw_memory_primitive`, std-only): compiled through the IR with every native program (loader `opts.runtime`). The lowering calls it in three ways: `myla_runtime_function(prim)` turns `__str_concat`, `__read`, `__stat`, … into `std$rt$<name>` (`Lower.rt_call`); `CodeGen.rt_exec()` aliases runtime entry names to std.rt functions (`__exit_program` → `std$rt$exit_program`); direct `Inst.Call("std$fmt$fmt_int")`, `std$slice$take`, `trap_text_fn`. Every name a back end calls must be in `checker.backend_std_functions()` (else `request_fn` panics "the checker never marked as called"; `test_lazy_std.py` greps the back ends for them).
3. **IR routines generated per type** in lower.my (drops, clones, walks, deep copies, `==`, hash, map find/put, env routines, partials, `__new` frame constructors, `__compose_call`), requested through `Want`/`type_jobs`/`need_*` and emitted by `emit_routine`/`emit_drop_helpers`.

`std.platform` is chosen per target by the loader (`for_target`: `platform_aarch64.my`, `platform_wasm.my` replace `platform.my`).

## Interpreter and parity

`interp.my` walks the checked AST with `Value` (`VInt(int64)`, `VStruct(name, fields, vals)`, `VList`, `VMap`, `VActor` …), integer widths and print/format from `resolved`. Builtins: `eval_name_call` (big if-chain on the name), methods `eval_method_call` → `builtin_method` → the same; primitives `net_primitive`, `term_primitive`, `notify_primitive`, `lot_primitive` (the host's own I/O through the interpreter binary's std). Runtime errors: `self.fail(e, msg)` → `RtError{msg, line, col, sp, node}` → `runtime error: msg` + `--> file:l:c`. Native code must print the same message at the same position (`trap_messages` in codegen.my, `trap_value_ir` + std.rt `*_text` for errors with values, D183).

Parity rules: interpreter output == native output on x86-64 == aarch64 == wasm32, except D175: `myla run`/`test` and `build --checked` trap integer overflow, a plain `build` wraps; the interpreter runs tasks one at a time, native in parallel.

## Bootstrap and seeds

`scripts/bootstrap.sh [OUT]`: stage0 = `as`+`ld` of `bootstrap/seed.s` (aarch64 host: `seed-aarch64.s`; `scripts/host.sh`); stage0 builds `tools/embed/main.my` → `embed lib selfhost/embedded_std.my` (rewrites it only if `lib/` or the AST/parser changed it); stage0 compiles `selfhost/gen_main.my lib` → `gen_tool` (stage 1); gen_tool → `stage2.s`; stage2 → `stage3.s`; `cmp stage2.s stage3.s` (fixed point); stage3 builds `build/myla` (`selfhost/main.my`) and `build/myla-lsp`, checks a type error exits 1 and the LSP answers. About 17 s on 2026-11-13 at `706eaec`.

`scripts/update-seed.sh`: bootstrap into `build/seed-update`, `myla check` of the eight implicit modules whole, then `seed_compile` stage3's output for both targets with an empty embedded_std (MYLA-431) under a header (commit, sha256). Commit `bootstrap/seed.s`, `bootstrap/seed-aarch64.s`, `selfhost/embedded_std.my`. `scripts/check-seed.sh` (CI `bootstrap` job, optional pre-push hook) fails when they aren't the current compiler's.

What stage 0 (the old seed) compiles: `gen_main.my`'s closure — anf, ast, astcache, checker, codegen, diag, dwarf, embedded_std, hoist, inline, ir, ir_a64, ir_util, ir_wasm, ir_x86, lexer, loader, lower, ownership, parser, ranges, runtime_*, ssa, stdroot, tokens, unicode, util — plus `tools/embed` (std.args) and these std modules: rt, platform, fmt, slice, num, io, ioerror, fs, process, bytes, and the implicit str, char, int, list, option, map, hash. Not compiled by the seed: interp, driver, main, repl, harness, project*, fetch, test_programs, play_main, the `*_main` drivers, tools/lsp (stage 3 builds them).

**Consequences (D156 and its exception):**
- The code that implements a feature must compile with the previous seed: no use of the new syntax, builtin method, primitive or runtime variable in that closure until a seed knows it. An unknown primitive is `type error: unknown function '__nope64'` in the seed's checker; a runtime variable the seed's prelude doesn't define is `undefined reference to '__no_such_var'` at stage 1's link.
- So a feature the library or compiler wants to use goes in three commits: (1) the compiler side (checker, interpreter, lowering, backends, runtime labels; std.rt may define but not yet use it); (2) a **Stage:** commit that only runs `scripts/update-seed.sh` and commits the three generated files; (3) the use in `lib/std`/`selfhost`. Examples: ca34622 → 07cd9dc (runtime variable `__exit_hook`, D187) → 821f6c8; 8481483 → 809d8f8 (`__read_bytes`, `__write_bytes`, "so that std.io, std.fs and std.process, which the compiler imports, can call them"); 0d81ef3 → 3d31aca → 6875b42 (`wrapping_*` builtin methods; 0d81ef3: "use the plain operators until the seed knows the builtins").
- Otherwise one seed per pull request, in its last commit (a PR that changes `selfhost/` or `lib/std/`); intermediate commits may have stale seeds.
- A pure Myla addition to `lib/std` that uses only existing features needs no staging (it is source to the seed).

## Checklist: adding a language feature

Order of work: grammar → lexer/parser → AST (only if no desugaring fits) → loader → checker → interpreter → lowering/IR/backends → tooling → tests → docs. Write the test first (a burn test program that fails), keep the old seed able to compile your implementation.

**0. Decide the encoding.** Prefer a parser desugaring into existing nodes (if-expr a7dcd66, if let 284c878, compound assignment f7294b1, slices/`^` 00ccfb0: "so every expression walker already covers them"); then the work is parser + checker (types, messages) + interpreter/lowering only where semantics differ. A new `ExprKind`/`StmtKind` variant means visiting every walker (defer ae328a7 touched ast, astcache, checker, codegen, interp, loader, lower, parser, tools/lsp/resolve). Library semantics both runners share go in a `lib/std` module (00ccfb0 added `std.slice`; the interpreter imports it, the lowering calls `std$slice$take`, listed in `backend_std_functions`).

**1. Syntax.** `grammar/myla.ebnf` (the source of truth for syntax; mirror the rules in `docs/Language/Grammar.md`, compared by `test_grammar`); then `scripts/gen_treesitter.sh` regenerates `editor/tree-sitter-myla/grammar.js`, `queries/highlights.scm` (from `tools/grammar/highlights.scm`) and `src/` (needs `npm install` there). Keywords: `tokens.keywords()` is pinned to the retired Python lexer's list (`test_grammar.test_the_keyword_list_is_the_lexer_s`), so a new word is a soft keyword: an IDENT checked by lexeme where it can only mean the keyword (`defer`: `k == IDENT && lexeme == "defer" && peek_kind_at(1) == LBRACE` in `Parser.statement`), declared `@soft "word"` in the EBNF. Hand-written lists to update too: `tools/lsp/features.my` `completion_keywords()`, `vscode-extension/myla/syntaxes/myla.tmLanguage.json` (both lacked `defer` at 706eaec, [[MYLA-582]]).

**2. Lexer** (`lexer.my`): only for new tokens/operators (`@adjacent` in the EBNF for joined tokens like `+=`); `TokenKind` in `tokens.my`, `kind_name`.

**3. Parser** (`parser.my`): statements in `Parser.statement` (before `assign_or_expr`), expressions at their precedence level (`pipe` → `logic_or` → … → `unary` → `postfix` → `primary`), patterns in the pattern functions. Build nodes with `mk_expr`/`mk_expr_from`/`mk_stmt`/`mk_stmt_from` (ranges via `span_from`), new ids with `fresh()`; errors via `expect`/the pending-error mechanism (recovery `recovered`/`sync`). Add `#test` cases with `expr_of("…")`/`stmt_of("…")`.

**4. AST** (if a new variant): `ast.my` enum + `dump_expr`/`dump_stmt` + `names_in_expr`/`names_in_block`; `astcache.my` `Writer.expr`/`Writer.stmt` and `Reader.expr_kind`/`Reader.stmt_kind` (a new numeric tag; the embedded parse changes, so embedded_std.my changes at the next bootstrap).
  Walkers with an exhaustive `match` fail to compile when you forget them (ast dump, astcache, `check_stmt`, `exec_stmt`, `Lower.stmt_body`, `tools/lsp/resolve.my` `Resolver.stmt`); walkers with a `_ =>` fallback silently skip it, so grep for a sibling variant (`grep -n "StmtKind.DeferS\|ExprKind.Await"`) and visit each: `loader.my` `Renamer.stmt`/`expr` (`_ => s.kind`: forgetting it leaves names unqualified → "unknown name" in modules), `checker.my` `Effects.stmt`, `Reads.stmt`, `Reentrancy.stmt`, `fd_stmt`/`fd_expr` (`fill_in`: default arguments, `for` over an iterator; a skipped statement keeps calls without their defaults), `codegen.my` `scan_stmt`/`scan_expr` (kept params), `free_block`/`free_expr` (lambda captures), `may_write_stmt`/`may_write_expr`, `lower.my` `resized_in_stmt`/`resized_in_expr`, `mentions_any`, `settled_operand`, `anf.my` `Norm.stmt`/`stmt_suspends` (anything that may contain `await`), `ast.my` `names_in_block`.

**5. Checker** (`checker.my`): types in `infer_node` (dispatch) → your `infer_*` returning `Result<Option<Type>, CheckErr>`, or `check_stmt`; record types with `record_type` (done by `infer_node`); errors `Err(terr_at(e.line, e.col, e.sp, "message"))`, notes as `Note{label: "help"|"note", …}`; context flags on `Checker` (e.g. `defer_at` forbids `return`/`?`/`await` inside a `defer`). Desugared forms: reword messages by marker (`if_worded`). Anything the back end needs that only the checker knows goes in a side table keyed by node id (`static_calls`, …) and is copied into `CodeGen` in `new_codegen`.

**6. Interpreter** (`interp.my`): `Interp.eval` (expressions) / `exec_stmt` (statements), async path `exec_async`/`Norm` when it can contain `await`; scopes `RtFrame{names, vals, defers}`; runtime errors `self.fail(e, msg)` with exactly the native message.

**7. Lowering** (`lower.my`): `Lower.expr` (scalar result in a temp), `Lower.addr` (aggregate: address of storage, `self.into` to build in place), `Lower.stmt_body`; control flow with `new_block`/`start`/`finish(Term)`/`leave`; ownership: `own(slot)`, `begin_temps`/`end_temps`, `drop_owners(depth)` on every scope exit (`defer` hooks in there: `emit_defers`), `retain`, `took`, `moved`; traps `Term.Trap(kind, pos)` / `Inst.Check(v, kind, pos)`; unsupported shapes `self.unsupported("…")` (becomes `internal error: X can't be lowered to the IR` in `take_ir`); user-facing refusals (limits, `become` past six words) as `CheckErr` in `self.refused`. If only existing `Inst`s are used, the passes and all three backends work unchanged — the common case.
  A new runtime error kind: `trap_labels` and `trap_messages` in codegen.my (both lists, same order; the `#test` cases there), then the backends' preludes pick them up; with values, `trap_text_fn` + a std.rt `*_text` function + `backend_std_functions`.
  A new `Inst`/`Term`/`Intrinsic`: `ir.my` (enum, `render_inst`/`render_intr`, `inst_uses`, `inst_defs`, `touches`, `verify`/`step` if it touches ownership, `intrinsic_arity`/`intrinsic_gives`), every pass that matches instructions (`inline.my`, `ssa.my`, `hoist.my`, `ranges.my`, `ownership.my`), all three backends (`ir_x86.my` selection and `clobbers`/register allocation, `ir_a64.my`, `ir_wasm.my`), and the contract section of `docs/Architecture/IR.md` plus `test_ir_contract.py`.

**8. Builtin methods.** Prefer Myla code: a method in an `impl` of the built-in type in the implicit std modules (`lib/std/str.my` `impl str`, `list.my` `impl<T> [T]`, `map.my`, `int.my`, `char.my`, `option.my`, `hash.my`): no compiler change, both runners run the same code; check the module whole (`build/myla test lib/std/str.my --stdlib lib`; update-seed refuses an implicit module that doesn't check whole). Only for things that need the machine (one instruction, raw cells) add a compiler builtin, as `wrapping_*` did (0d81ef3): `checker.my` `is_builtin_func`, `builtin_method_name`, `builtin_method(t, m)`, `receiver_only`, an `infer_*` (e.g. `infer_wrapping`), arity message `method_arity`; `interp.my` `eval_name_call`/`eval_method_call` (+ `names_a_builtin`); `codegen.my` `is_builtin_call_name`; `lower.my` `Lower.call` (the `GetField` branch rewrites `recv.m(a)` to `m(recv, a)` when `builtin_method` holds, then the name if-chain); tests `test_builtin_methods.py`. Then staging before selfhost/lib use it.

**9. Runtime primitive** (`__name`, std-only): 8481483 is the template — `checker.my` (`is_builtin_func` and the family predicate: `is_raw_memory_primitive` / `is_platform_primitive` / `is_net_primitive` / `is_term_primitive` / `is_notify_primitive`, its signature, e.g. `infer_platform_primitive`, `net_primitive_sig`), `codegen.my` `is_builtin_call_name`, `interp.my` (host implementation), `lower.my` (`io_call`; usually `myla_runtime_function` → `std$rt$<name>`, or an `Intr`, or a `Global`), `lib/std/rt.my` (the implementation over `std.platform` for each target's platform file), `docs/Language/Targets.md`, `tests/burn/test_platform_primitives.py`. Then a Stage commit before std uses it.

**10. Runtime variable**: a data label in `CodeGen.assemble_source` (x86-64; ca34622 added `__exit_hook: .skip 96`) and in `runtime_a64.my` / `runtime_wasm.my` preludes as needed; a per-worker one gets a `tls_offset` slot (and `TLS_SIZE`). std.rt reads it with `__rt_get`/`__rt_addr`. Stage the seed before std.rt uses it.

**11. A new type** (built-in): `checker.my` `Type` variant (exhaustive matches everywhere: `type_name`, `subst_type`, unify, …), its spelling in the type parser/resolver, layout in `codegen.my` (`size`, `is_aggregate`, `is_cell_t`, `owns_heap`, `type_key`, `mono_token`, `dbg_*`), ownership routines in lower.my (drop/clone/walk/deep/eq/hash), `Value` in interp.my, astcache only if `TypeKind` changes. Big: prefer a library struct (std.deque, std.bigint are libraries).

**12. Tests** (Python burn tests in `tests/burn/`, run `python3 -m unittest tests.burn.test_<x>`, not the whole suite while iterating):
- A feature test `tests/burn/test_<feature>.py` with a `PROGRAM` run by `run_source_both_now` (interpreter and native must agree) and error cases; register its program for the other targets: `PROGRAMS["<feature>"] = test_<feature>.PROGRAM` in `test_aarch64.py` (test_wasm reuses it); suites run on targets are listed in `tests/burn/_targets.py` (`SUITES`, excuses `SKIP`), `python3 scripts/test-target.py aarch64-linux test_<feature>`.
- Codegen corners: a program in `test_compiler_parity.py` `PROGRAMS`.
- Rejections: one file per diagnostic in `examples/errors/` (`lex_`, `parse_`, `type_`, `module_`, `runtime_` prefix), first line `//~ <stage> error: <substring>`, optional `//~ span:`, `//~ errors: n`/`//~ next:`, `//~ note:`/`//~ help:`, runtime ones `//~ native: runtime error: …` and `//~ checked`; a sibling `.stderr` pins the whole rendering (`TestPinnedDiagnostics`).
- An example in `examples/` with `#test` cases on every value-returning function, listed in `test_examples_run.py` `EXPECTED` and `test_examples_compile.py` `EXAMPLES` (the test fails on an unlisted file).
- `#test` cases on new selfhost functions (target 80 %, D109), built with the factories `checker_on(src)`, `codegen_on(src)`, `lower_on()`, `interp_on(src)`, `parser_on(src)`, `expr_of`/`stmt_of`/`block_of`/`pattern_of`/`fun_of`; run `build/myla test selfhost/lower.my` etc.
- A test that would ask the retired Python oracle (`@golden`) about a new program fails "no recorded answer": give it its own expectation.
- Grammar: `test_grammar.py` (wiki rules == EBNF, generated files current, random programs from the grammar parse, tree-sitter parses every repo .my file).
- IR: `--emit-ir` on a probe (`build/stage3 p.my lib --emit-ir`) to see the lowering; `test_ir_contract.py` for new instructions.
- Last: `scripts/bootstrap.sh` (fixed point), then `scripts/update-seed.sh` as the PR's last commit.

**13. Docs and records**: `docs/Language/<page>.md` (Statements, Expressions-and-operators, Collections-and-strings, Types, …; every ```` ```myla ```` block is a tested program, `fragment`/`error` info strings otherwise), `docs/Language/Grammar.md`, `docs/Project/Decisions.md` (a new row at the top: `| Dnnn | date | **decision** … | reason |`), the task file in `tasks/<epic>/MYLA-n.md` (status, `## Evidence`), `docs/Development/Testing.md` (burn test table), the `myla` skill (`.claude/skills/myla/`, its `reference/` files included, mirrored identically in `.agents/skills/myla/`), and the architecture page of any stage you changed.

## Conventions inside selfhost

- No globals, no module-level maps: state is a struct passed as `var self` (`Parser`, `Checker`, `Interp`, `CodeGen`, `Lower`), tables are lists searched with loops or maps keyed by node id or name; updating nested state means rebuilding values.
- Errors: lexer and parser record a `Diag{kind, line, col, sp, msg}` and skip ahead (no `Result` plumbing); loader returns `Result<_, Report>`; checker returns `Result<_, CheckErr>` and propagates with `?`, `run_all` collects up to 20 (`MAX_ERRORS`, D80); `poisoned()`/`TError` stop cascades; interpreter `fail` → `RtError`; the CLI renders everything with `diag.render(Report)` (`type_errors(prog, errs)` attaches files). A broken invariant in a back end is `panic("internal error: …")`, never a user diagnostic.
- Messages: lower-case, the construct quoted (`'defer'`), help notes say what to write instead; they are pinned by the error corpus, so changing one updates its corpus file.
- Comments cite the task and decision (`(MYLA-251)`, `(D135)`) and say why; every new value-returning function gets `#test(args)[expected]` cases (a trailing `// label` names one).
- Synthesized nodes use fresh ids and `%`-names; synthesized nodes without a source range get one caret.
- Shared helpers: `is_aggregate`, `is_cell_t`, `is_list_t`/`is_map_t`/`is_str_t`, `list_elem`, `map_key`/`map_val`, `tuple_elems`, `type_key`, `mangle_fn` (codegen.my); `subst_type`, `type_name`, `unify_param` (checker.my); `reachable_blocks`, `successors`, `inst_uses`/`inst_defs`, `touches` (ir.my, ir_util.my).
- `snake_case` functions, `PascalCase` types, four spaces; comments in full sentences.
