---
id: MYLA-71
title: Emit DWARF line tables so gdb can step through Myla source
type: feature
status: review
priority: medium
labels: [native-backend, debugging, tooling]
---
The first, cheap step of [[MYLA-66]]. The GNU assembler builds the DWARF `.debug_line` table from two directives:

```asm
    .file 1 "examples/structs.my"     # once per source file
    .loc 1 12 5                       # before the code of the statement at line 12, column 5
```

Every AST node already carries its line and column, and labels are already `myla_<name>`, so with these directives `gdb ./prog` can `break structs.my:12`, `step`/`next` through Myla lines, and show Myla line numbers in backtraces.

**Proven (2026-10-25):** adding one `.file` and two `.loc` lines by hand to the assembly of a small program was enough: `gdb -batch -ex 'break p.my:2' -ex run -ex bt` stopped at `p.my:2`, printed `let c = a + b`, and showed the backtrace `myla_add () at p.my:2` ← `myla_main` ← `_start`.

## Done when

- [x] `myla build -g` emits `.file` per module and `.loc` at each function, statement and expression-bodied match arm in [[src/myla/compiler/codegen_x86.py]]; lambdas use the file they are created in; the loader records each function's `source_path`
- [x] Runtime helpers carry no source line (`.loc <file> 0 0` after each function)
- [x] Without `-g` the output is unchanged
- [x] Tests first: `tests/unit/test_compiler.py::TestLineTables` (directives, files of imported modules, lambdas, line 0 after functions) and `tests/burn/test_debug_info.py` (readelf sees the lines; `-g` doesn't change behaviour; gdb stops on `prog.my:2` and shows the Myla backtrace)
- [x] Documented with a real gdb session on [[Development/Debugging]]
- [ ] The same in [[selfhost/codegen.my]]: unblocked: positions are per file since [[MYLA-30]], and the loader's `Loaded.spans` maps each node id to its file ([[MYLA-28]])
