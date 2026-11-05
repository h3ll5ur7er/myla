# Architecture

How the toolchain is built. It is written in Myla, in `selfhost/` (the compiler, the interpreter, the CLI) and `tools/` (the language server, the grammar generator), with the standard library in `lib/std/`; it bootstraps from a committed seed, its own assembly ([[Development/Bootstrap]], D101).

Until November 2026 a Python toolchain in `src/myla/` was the bootstrap and the reference the self-hosted one was tested against, and the self-hosted stages were ported from it nearly line for line ([[Architecture/Self-hosted-compiler]]). It was retired by D101 ([[MYLA-219]]); the branch `backup/python-toolchain-final` keeps it. The pages on the lexer and parser, the module loader, the type checker, the interpreter, monomorphization and the native backend were written for it: the design they describe is the self-hosted toolchain's too, but where they name functions and modules of the Python implementation, that code is gone.

[SUBPAGES]

## The pipeline

```mermaid
flowchart LR
    entry["entry .my"] --> loader["Module loader<br/>loader.my"]
    loader -->|"each module:<br/>lexer.my → parser.my"| merged["linked declarations<br/>(names qualified as module$name)"]
    merged --> checker["Type checker<br/>checker.my"]
    checker -->|"checked declarations,<br/>types by node id"| interp["Interpreter<br/>interp.my"]
    checker --> cg["Code generator<br/>codegen.my<br/>(monomorphizes as it goes)"]
    cg -->|"each function"| ir["IR<br/>lower.my → ir.my (verified)"]
    ir --> own["ownership.my<br/>(counts made plain)"]
    own --> x86["ir_x86.my"]
    own --> a64["ir_a64.my"]
    own --> wasm["ir_wasm.my"]
    x86 -->|".s"| asld["as + ld"]
    a64 -->|".s"| a64ld["clang + ld.lld"]
    wasm -->|".s"| wasmld["clang + wasm-ld"]
    asld --> elf["static ELF, x86-64"]
    a64ld --> elf64["static ELF, aarch64"]
    wasmld --> mod["wasm module, WASI"]
    interp --> out["run / test / repl"]
```

| Module | Role | Page |
| --- | --- | --- |
| `main.my`, `driver.my` | The CLI `build/myla`: commands `run`, `test`, `build`, `check`, `repl` and the project commands; what they do with one entry file | [[Getting started]] |
| `tokens.my`, `lexer.my` | Source → tokens; f-strings lowered here | [[Architecture/Lexer-and-parser]] |
| `ast.my`, `parser.my` | Tokens → AST; `|>` and `return a, b` lowered here | [[Architecture/Lexer-and-parser]] |
| `loader.my` | Import graph → one program with qualified names | [[Architecture/Module-loader]] |
| `checker.my` | Type representation, the checker, the types of every expression | [[Architecture/Type-checker]] |
| `interp.my`, `anf.my` | Tree-walking interpreter and `#test` runner; async bodies normalized for its async evaluator | [[Architecture/Interpreter]] |
| `codegen.my` | The code generator: the worklist of functions and their concrete copies, layouts, the module's text, debug information (still with x86-64 code in it, [[MYLA-262]]) | [[Architecture/Monomorphization]], [[Architecture/Native-backend]] |
| `lower.my`, `ir.my`, `ownership.my`, `inline.my`, `ssa.my` | Every function through the IR: lowering, verifier, the ownership instructions made plain, inlining, slots promoted to values | [[Architecture/IR]] |
| `ir_x86.my`, `ir_a64.my`, `ir_wasm.my` | The backends: the IR to x86-64 (with register allocation), aarch64 and wasm32 | [[Architecture/Native-backend]] |
| `runtime_x86.my`, `runtime_a64.my`, `runtime_wasm.my` | Each target's hand-written runtime: start, traps, system calls, threads, the jumps into frames | [[Architecture/Native-backend]] |
| `play_main.my`, `tools/wasm/` | The checker and interpreter as wasm for a page, and the WASI shim that runs it | [[Architecture/Native-backend#the-page-api]] |
| `dwarf.my` | The fixed parts of the `-g` debug information | [[Development/Debugging]] |
| `diag.my` | Rendering an error with its source line and carets | below |
| `repl.my` | `myla repl` | [[Architecture/Self-hosted-compiler]] |
| `project.my`, `project_cmd.my`, `fetch.my` | The project tool | [[Architecture/Project-tool]] |
| `lib/std/*.my` | The standard library, in Myla; `rt.my` is the native runtime, `platform*.my` the platform layer per target | [[Language/Standard-library]] |
| `lib/debug/myla_gdb.py` | gdb pretty-printers, embedded in `-g` binaries (D82) | [[Development/Debugging]] |

The toolchain bootstraps on x86-64 and aarch64 Linux from that machine's seed and needs only its `as` and `ld` (D127), which also build programs for that machine, its default target. Building for the other machine needs clang and `ld.lld`, for wasm32 clang and `wasm-ld` (D125); running those programs on another machine needs `qemu-aarch64` or Node. The tools beyond the compiler (the language server, the grammar generator) are written in Myla too, in `tools/`.

## Principles

- **One front end, two ways to run.** The interpreter and the code generator consume the same checked declarations, and the checker records what they need in side tables keyed by node id (`resolved`, the type of every expression, and others), so neither infers anything again.
- **Desugar early where no types are needed.** f-strings disappear in the lexer, `|>` and `return a, b` in the parser. `?`, `>>` composition, `_` partial application, operator overloading and `#derive(Eq)` are checked by the checker and carried out by the interpreter and the lowering from its records. (The Python checker replaced them with desugared nodes instead.)
- **The interpreter and native code agree.** Every example's native output is compared with the interpreter's; a difference is a bug in one of them ([[Development/Conventions]]).
- **Simple over clever, then measured.** The first native backend had no register allocator and kept every value in a stack slot (D1, D2); the IR (D79) made frame layout and ownership explicit data that can be printed and verified, and the optimisations since were each measured ([[Development/Benchmarks]]): register allocation on x86-64 ([[MYLA-257]]), inlining, slots as values (D123). Each new backend starts simple too: aarch64 with every temporary in a frame cell, wasm with a dispatch loop.
- **A target is a translation.** The front end, the lowering and the ownership rules are the same for every target; a backend translates the IR and brings a small runtime file and a platform module. What isn't yet so is listed on [[Project/Reflection-2026-11]].

## Diagnostics

The lexer and the parser report a `Diag` (`kind`, position, range `sp`, message; [[selfhost/tokens.my]]), the checker a `CheckErr`, the declaration it comes from naming its file; the CLI turns them into a `Report` ([[selfhost/diag.my]]): `kind` used as the prefix (`lex error`, `parse error`, `type error`, `module error`, `runtime error`), message, file, position and range, the errors found after it (`more`) and its notes. The parser and the checker report up to 20 errors per run (`MAX_ERRORS`, D80): the parser resumes at the next statement, impl member or declaration, the checker checks every function on its own once its tables are built; the lexer, the loader and the interpreter stop at their first error. A stage gives the first error it found, the one a single-error run reported, with the others in its `more` in the order they were found. An error records the file its position refers to (MYLA-10). `diag.render` prints each error with that file's source line and carets under the error's range, a blank line apart, and after several errors a summary line, `error: aborting due to 3 previous errors`; the language server publishes each error for its file.

The range (`span`: start line and column, and the position just past the end) comes from what the error is about (D74, [[MYLA-65]]). An error takes its range from a token or a syntax node: a token from the lexer, a node from the parser, which records the range of the tokens it consumed for it, from the first to the last (so `f(1, 2)` and `a + b` include their left operand, and the parentheses around an operand belong to the enclosing expression, not to the operand). A lex error runs from its position to where the lexer stopped (`"oops` for an unterminated string, `10i9` for a bad suffix). The carets cover the range's part on the error's line, to the end of the line when the range goes on (a declaration shows its first line), and always the error's column, which stays where it was: for `a + b` the operator, for a call its `(`. Nodes the checker synthesizes have no range and get one caret.

```
type error: unknown function 'nope'
  --> x.my:2:17
  |
2 |     let x = nope(1)
  |             ^^^^^^^
```

## More

- [[Architecture/Self-hosted-compiler]]: the files, how a compiler is written in Myla, how it was brought up against the Python toolchain.
- [[Architecture/Rust-edition]]: a separate dialect and toolchain in Rust, removed in October 2026 (history note).
- [[Architecture/Editor-tooling]]: language server, VS Code extension and its debugger, the grammar description and the tree-sitter grammar generated from it.

## Built since the first design

- [[Architecture/Project-tool]]: `myla` as a project tool like cargo, with a manifest (`myla.toml`), path and Git dependencies and the commands `new`, `build`, `run`, `test`, `check`, `fetch` and `clean` (D73, [[MYLA-64]]).
- [[Architecture/IR]]: the mid-level IR between the checker and the self-hosted backend: three-address code on basic blocks with explicit reference counting and a verifier; every function goes through it since [[MYLA-107]] (D79, D85).

- The runtime in Myla (`std.rt` over `std.platform`, [[MYLA-162]], D117) and backends of Myla's own for Linux on aarch64 ([[MYLA-163]]) and wasm32 on WASI ([[MYLA-158]], D125), with the checker and interpreter in a page: [[Architecture/Native-backend]]. What they taught: [[Project/Reflection-2026-11]].

Not built yet: macOS and Windows ([[MYLA-164]], [[MYLA-165]]), after the work the reflection lists ([[MYLA-62]]).

The original v0.0 design sketch of this architecture is [[Archive/architecture]].
