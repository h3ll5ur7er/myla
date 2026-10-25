---
id: MYLA-71
title: Emit DWARF line tables so gdb can step through Myla source
type: feature
status: todo
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

- [ ] `myla build -g` (or always, if the size cost is small) emits `.file` per module and `.loc` before each statement (and each match arm) in [[src/myla/compiler/codegen_x86.py]]; the loader passes each declaration's source path along (shared need with [[MYLA-10]])
- [ ] Runtime helpers carry no `.loc` (they show as assembly in gdb)
- [ ] A manual check documented on [[Development]]: break, step, backtrace in `examples/structs.my`
- [ ] The same in [[selfhost/codegen.my]] (the fixed point must still hold: the directives are deterministic)
