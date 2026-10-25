# Self-hosted compiler

`selfhost/` is the Myla toolchain written in Myla: lexer, parser, checker, x86-64 code generator, a module loader and an interpreter. Compiled by the Python toolchain, it compiles itself to a byte-identical fixed point ([[Development/Bootstrap]]). The Python toolchain remains the reference it is tested against.

[TOC]

## Files

| File | Lines | Role |
| --- | --- | --- |
| `tokens.my` | 150 | `#derive(Eq) enum TokenKind` (~80 variants), `struct Token`, keyword lookup as an `if` chain, `kind_name` |
| `util.my` | 100 | UTF-8 encoding, escaping for canonical dumps, character classes, digit parsing |
| `lexer.my` | 620 | Decodes the source to code points (so columns match Python), scans tokens, lowers f-strings like the Python lexer; errors `panic` |
| `ast.my` | 380 | AST nodes as wrapper structs `{id, line, col, kind}` around `enum …Kind`; unique node ids; the canonical S-expression dump |
| `parser.my` | 1390 | Recursive descent with the same precedence levels and desugarings as `parser.py` |
| `checker.my` | 3570 | Name tables, inference, generics, traits, exhaustiveness, const folding; records each expression's type in `resolved: [int32: Type]` keyed by node id |
| `codegen.my` | 6200 | Monomorphizing code generator and the whole runtime, as assembly text |
| `interp.my` | 1830 | Tree-walking interpreter over checked declarations |
| `loader.my` | 170 | Finds imports, strips them, concatenates modules' source (dependencies first) |
| `gen_main.my` | 50 | The bootstrap compiler: `gen_main <file.my> <stdlib_root>` → assembly on stdout |
| `main.my` | 200 | The self-hosted CLI: `myla run|test|build <file> [-o out] [stdlib_root]`; `build` runs `as`/`ld` through `std.process.run` |
| `lex_main.my`, `parse_main.my`, `check_main.my`, `interp_main.my`, `amalg_main.my` | 30–40 each | Drivers for the differential tests (canonical tokens, canonical AST, `ok`/`err line col kind`, interpreted output, amalgamated source) |
| `probe_*.my` | 15–20 each | Bring-up scratch files, unused ([[MYLA-34]]) |

## Writing a compiler in Myla

Myla has no global variables and no module-level maps, and everything is a value, which shapes the code:

- Symbol tables are lists of records searched with `while` loops (`StructInfo`, `EnumInfo`, `FuncSig`, `MethodEntry`, `TraitInfo` in the checker; `funcs`, `str_texts` in codegen).
- Scopes are lists of frames: `[Frame{names: [str], binds: [Binding]}]`.
- Maps serve as side tables keyed by node id (`resolved`, and in codegen `locals`, `match_scrut`, `match_bind` keyed `"patid:name"`).
- `Type` is an enum: `TInt(width, signed) | TFloat | TChar | TBool | TStr | TSB | TStruct(name, args) | TEnum(name, args) | TTuple | TList | TMap | TFunc(params, Option<ret>) | TParam | TSelf`.
- Errors are `Result` values propagated with `?`; a type error is just `CheckErr{line, col}` without a message.
- State lives in structs passed around with `var self` methods; updating a nested value means rebuilding it.

## Pipeline differences from the Python toolchain

| Area | Python toolchain | Self-hosted |
| --- | --- | --- |
| Modules | Qualified names, privacy, packages | Text concatenation ([[MYLA-30]]) |
| Monomorphization | Separate pass, then a second check | During code generation, with a substitution list |
| Floats | Full support | None: the AST keeps only the literal's suffix ([[MYLA-29]]) |
| Diagnostics | Messages with file positions | Positions only, offset by the prelude ([[MYLA-28]]) |
| Runtime errors | Messages | Silent `__trap` (exit 1) |
| Heap | 1 GiB arena, one exact-fit free list | 4 GiB arena, size-class free lists, but `__free` returns immediately ([[MYLA-22]]) |
| Closure environments | Captures retained and dropped | Captures neither retained nor dropped |
| Stdlib root | Built in | Must be passed as an argument ([[MYLA-31]]) |

The calling convention, value layouts, list/map/builder runtimes and even the right-to-left operand order are ported nearly line for line from [[Architecture/Native-backend]].

## How it was brought up

Each stage was ported and tested against the Python oracle before the next one (v0.6–v0.9):

1. **Lexer**: `myla tokenize --canonical` vs `lex_main`, byte for byte, on every example.
2. **Parser**: `myla parse --canonical` vs `parse_main`.
3. **Checker**: `myla check --canonical` vs `check_main`: same accept/reject and same error position on the examples and the error corpus.
4. **Code generator and loader**: native output of `gen_main`-compiled programs vs the interpreter.
5. **Fixed point**: the compiler compiles itself until the output stops changing.

The burn tests `tests/burn/test_selfhost_*.py` keep these gates; note they build the self-hosted tools with the **Python** backend, so they test the self-hosted front end, while only the bootstrap exercises self-compiled binaries ([[Development/Testing]]).

## Current state

- The three-stage fixed point holds: stage 2 and stage 3 output are identical (4.4 MB of assembly, 691 functions); stage 3 compiles the compiler in 1.5 s using 361 MB.
- Against the interpreter, the stage 3 compiler matches on 31 of 34 examples (`floats.my` drops every float line, `modules/main.my` fails to load its package, `args` differs only in argv[0]).
- The stage 4 CLI's `myla run` (the Myla interpreter, compiled) fails on programs that call methods ([[MYLA-21]]) and on floats.
- Further bugs: [[MYLA-23]] … [[MYLA-27]], [[MYLA-32]], [[MYLA-33]]. See [[Project/Known-issues]].
