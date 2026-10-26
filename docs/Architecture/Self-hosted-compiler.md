# Self-hosted compiler

`selfhost/` is the Myla toolchain written in Myla: lexer, parser, checker, x86-64 code generator, a module loader and an interpreter. Compiled by the Python toolchain, it compiles itself to a byte-identical fixed point ([[Development/Bootstrap]]). The Python toolchain remains the reference it is tested against.

[TOC]

## Files

| File | Lines | Role |
| --- | --- | --- |
| `tokens.my` | 150 | `#derive(Eq) enum TokenKind` (~80 variants), `struct Token`, keyword lookup as an `if` chain, `kind_name` |
| `util.my` | 100 | UTF-8 encoding, escaping for canonical dumps, character classes, digit parsing |
| `lexer.my` | 710 | Decodes the source to code points (so columns match Python), scans tokens, lowers f-strings like the Python lexer; the first error is returned with the Python lexer's message and position |
| `ast.my` | 380 | AST nodes as wrapper structs `{id, line, col, kind}` around `enum …Kind`; unique node ids; the canonical S-expression dump |
| `parser.my` | 1430 | Recursive descent with the same precedence levels and desugarings as `parser.py` |
| `checker.my` | 3760 | Name tables, inference, generics, traits, exhaustiveness, const folding; records each expression's type in `resolved: [int32: Type]` keyed by node id; type errors carry the Python checker's messages |
| `codegen.my` | 6200 | Monomorphizing code generator and the whole runtime, as assembly text |
| `interp.my` | 1830 | Tree-walking interpreter over checked declarations |
| `loader.my` | 990 | Module loader: resolves imports, parses each module once, qualifies module-level names (`id$name`), checks `pub`, folds `alias.member` ([[Architecture/Module-loader]]) |
| `diag.my` | 85 | Renders a diagnostic like the Python CLI: message, `--> file:line:col`, source line and caret |
| `gen_main.my` | 60 | The bootstrap compiler: `gen_main <file.my> <stdlib_root> [-g]` → assembly on stdout (`-g`: DWARF line tables, [[MYLA-71]]) |
| `main.my` | 190 | The self-hosted CLI: `myla run|test|build <file> [-o out] [-g] [stdlib_root]`; `build` runs `as`/`ld` through `std.process.run` |
| `lex_main.my`, `parse_main.my`, `check_main.my`, `interp_main.my` | 30–50 each | Drivers for the differential tests (canonical tokens, canonical AST, `ok` or `err line col kind: message`, interpreted output; `interp_main` goes through the loader and prints runtime errors like the Python CLI) |

## Writing a compiler in Myla

Myla has no global variables and no module-level maps, and everything is a value, which shapes the code:

- Symbol tables are lists of records searched with `while` loops (`StructInfo`, `EnumInfo`, `FuncSig`, `MethodEntry`, `TraitInfo` in the checker; `funcs`, `str_texts` in codegen).
- Scopes are lists of frames: `[Frame{names: [str], binds: [Binding]}]`.
- Maps serve as side tables keyed by node id (`resolved`, and in codegen `locals`, `match_scrut`, `match_bind` keyed `"patid:name"`).
- `Type` is an enum: `TInt(width, signed) | TFloat | TChar | TBool | TStr | TSB | TStruct(name, args) | TEnum(name, args) | TTuple | TList | TMap | TFunc(params, Option<ret>) | TParam | TSelf`.
- Errors are `Result` values propagated with `?`: a type error is `CheckErr{line, col, msg, decl}`, the declaration naming its file. The lexer and parser have no `Result` plumbing: they record their first error and skip to the end of the input.
- State lives in structs passed around with `var self` methods; updating a nested value means rebuilding it.

## Pipeline differences from the Python toolchain

| Area | Python toolchain | Self-hosted |
| --- | --- | --- |
| Modules | Qualified names, privacy, packages | The same since [[MYLA-30]] (small differences on [[Architecture/Module-loader]]) |
| Monomorphization | Separate pass, then a second check | During code generation, with a substitution list |
| Floats | Full support | Full support since [[MYLA-29]]: literals converted with integer arithmetic (`selfhost/floatlit.my`), the float runtime generated from the Python backend's (`scripts/gen_selfhost_runtime.py`) |
| Diagnostics | Messages with file positions | The same: lex, parse, module and type errors print exactly as in the Python CLI, file, source line and caret included ([[MYLA-28]]) |
| Runtime errors | Messages | The interpreter (`myla run`/`test`): the same messages and rendering since [[MYLA-32]]; native binaries: a silent `__trap` (exit 1, as the Python backend's, [[MYLA-17]]) |
| Heap | 1 GiB arena, size-class free lists up to 4 KiB | 4 GiB arena, size-class free lists (memory reused since [[MYLA-22]]) |
| Closure environments | `[drop fn][captures…]`, captures retained and dropped | The same since [[MYLA-22]]; compositions and partial applications own their parts too |
| Stdlib root | Built in | Must be passed as an argument ([[MYLA-31]]) |

The calling convention, value layouts, list/map/builder runtimes and the evaluation order are ported nearly line for line from [[Architecture/Native-backend]].

## How it was brought up

Each stage was ported and tested against the Python oracle before the next one (v0.6–v0.9):

1. **Lexer**: `myla tokenize --canonical` vs `lex_main`, byte for byte, on every example.
2. **Parser**: `myla parse --canonical` vs `parse_main`.
3. **Checker**: `myla check --canonical` vs `check_main`: same accept/reject and same error position on the examples and the error corpus.
4. **Code generator and loader**: native output of `gen_main`-compiled programs vs the interpreter.
5. **Fixed point**: the compiler compiles itself until the output stops changing.

The burn tests `tests/burn/test_selfhost_*.py` keep these gates; note they build the self-hosted tools with the **Python** backend, so they test the self-hosted front end and, through the programs `gen_main` compiles, its code generator and runtime (including the arena-reclaim stress programs, with a memory bound), while only the bootstrap exercises self-compiled binaries ([[Development/Testing]]).

## Current state

- The three-stage fixed point holds: stage 2 and stage 3 output are identical (5.8 MB of assembly); stage 3 compiles the compiler in 1.3 s with a 163 MB peak (359 MB while `free` was disabled, [[MYLA-22]]).
- Against the interpreter, the stage 3 compiler matches on 33 of 34 examples (`args` differs only in argv[0]: the binary's path instead of the source file's).
- The stage 4 CLI's `myla run` (the Myla interpreter, compiled) prints byte for byte what the Python CLI prints (stdout, stderr, exit code) on all 34 examples and the whole error corpus: lex, parse, type and runtime errors ([[MYLA-28]], [[MYLA-32]]). The program's `args()` is `[file]`, as under `myla run` without extra arguments (the self-hosted CLI takes no program arguments). The interpreter is slow on growing containers ([[MYLA-74]]).
- Further bugs: [[MYLA-23]] … [[MYLA-27]], [[MYLA-32]], [[MYLA-33]]. See [[Project/Known-issues]].
