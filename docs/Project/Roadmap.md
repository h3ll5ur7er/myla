# Roadmap

[TOC]

## Milestones

| Milestone | Theme | Status |
| --- | --- | --- |
| v0.0 | Python toolchain: front end, tree-walking interpreter, x86-64 compiler, `#main`/`#test` | Done |
| v0.2 | Data modelling: `enum` + `match`, tuples, generics (monomorphized), `Option`/`Result` + `?`, recursive enums, reference counting | Done |
| v0.3 | Collections and operators: lists, maps (copy-on-write), the string toolkit, `StringBuilder`, bitwise operators, casts, hex/binary/octal literals, `break`/`continue`, `const`, `assert`/`panic`/`unreachable` | Done |
| v0.4 | Abstraction: methods and `impl`, function types, lambdas and closures, `|>`/`>>`/`_`, traits, operator overloading, `#derive(Eq)`, bounds | Done |
| v0.5 | Modules and runtime: imports, `pub` and re-exports, the standard library, floats, `char` and UTF-8, freestanding I/O, generic traits, f-strings | Done |
| v0.6–v0.9 | Self-hosting bring-up: lexer, parser, checker, code generator and loader ported to Myla, each tested against the Python oracle | Done |
| **v1.0** | **Self-hosted: three-stage byte-identical fixed point** (30 June 2026) | **Done** |
| post-1.0 | Subprocesses (`std.process.run`), the self-hosted CLI with `run`/`test`/`build`, the language server, the VS Code extension, the Rust edition | Done (July 2026), with open issues |

The milestone numbering was locked by D23: self-hosting is the destination (v1.0), reached through the feature milestones. The detailed per-version designs are in [[Archive]].

## Next

1. **Make the existing toolchains correct.** The October 2026 review found parity and memory bugs; the urgent ones are in `todo`:
   - Python backend: [[MYLA-2]] (dangling match bindings), [[MYLA-3]] (aggregate field assignment), [[MYLA-4]] (the only red burn test), [[MYLA-10]] (errors in the wrong file).
   - Self-hosted compiler: [[MYLA-21]] (destructuring boxed enums, breaks the self-hosted `run`), [[MYLA-22]] (`free` disabled).
   - Rust edition: [[MYLA-36]] (silent miscompiles).
2. **Close the self-hosted gaps**: floats ([[MYLA-29]]), the module loader ([[MYLA-30]]), diagnostics ([[MYLA-28]]), so that the self-hosted toolchain can replace the Python one for everyday use.
3. **Performance**: the allocator ([[MYLA-16]]) and string reclamation ([[MYLA-18]]).
4. **Tooling**: language server precision ([[MYLA-51]]) and tests ([[MYLA-52]]), a REPL ([[MYLA-19]]).

## Proposed after 1.0

Ideas not yet decided or scheduled (from the decision log and the feature catalogue in [[Archive/future-features]]):

- compound assignment `+= -= *= /= %=`, `**` and `**=`;
- custom operators (D18) and user-defined macros / attributes;
- sets (D39: as a thin layer over maps);
- by-reference closure capture with `ref` (D15, D48);
- `#derive(Ord)`, trait objects, user-defined bounds beyond operators;
- associated functions (`Type.new()`), named-field enum variants (D32), `@` bindings and range patterns (D33);
- a package manifest and `exec` from the language runtime beyond `std.process` (D29).
