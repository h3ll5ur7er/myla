# Debugging

[TOC]

## gdb on native binaries

Build with `-g` to get a DWARF line table ([[MYLA-71]]):

```bash
python3 myla.py build examples/structs.my -o structs -g
gdb ./structs
```

Then break on Myla source lines, step line by line and read backtraces. A real session on `examples/structs.my` (gdb prints absolute paths in frames; shortened here):

```
(gdb) break structs.my:16
Breakpoint 1 at 0x40161b: file structs.my, line 16.
(gdb) run
3
4
Breakpoint 1, myla_manhattan () at structs.my:16
16	    return dx + dy
(gdb) bt
#0  myla_manhattan () at structs.my:16
#1  0x00000000004014f8 in myla_main () at structs.my:25
#2  0x0000000000401028 in _start ()
(gdb) next
7
28	    var moved = here
(gdb) next
29	    moved.x = 100
```

- Functions are named `myla_<name>` (`myla_main`, `myla_Point.len` for methods, `myla_geometry$area` for a function from module `geometry`, `myla___lambda_3` for lambdas, `myla_first__int32` for a generic instantiation). `break myla_main`, `break myla_Point.len` and `break myla_geometry$area` work as written. gdb guesses a demangling for `__` and shows the generic instance as `myla_first.int32` in frames; break on it by its label.
- Every statement and every expression-bodied match arm starts a line entry. Runtime helpers (`__alloc`, `__print_int`, …) have no source line; `step` into them shows assembly, `finish` gets you out.
- `-g` changes nothing else: the binary behaves exactly like one built without it (`tests/burn/test_debug_info.py`).

## The self-hosted compiler

The self-hosted compiler emits the same line tables with `-g` (`gen_main <file.my> <stdlib_root> -g`, or `myla build … -g` with the self-hosted CLI). The loader knows which node ids belong to which file (`Loaded.spans`), so each module gets its own `.file` entry. That makes the self-hosted compiler debuggable in its own source: build it with `-g` by the stage 3 compiler and break in the checker while it reports a type error:

```
$ build/stage3 selfhost/gen_main.my src/myla -g > gen.s && as --64 -o gen.o gen.s && ld -o gen_g gen.o
$ gdb -q -batch -ex 'break checker.my:2561' -ex 'run bad.my src/myla' -ex bt ./gen_g
Breakpoint 1, myla_checker$Checker.check_stmt () at selfhost/checker.my:2561
2561	                        if !type_eq(value_type, d) { return Err(terr(s.line, s.col, format("cannot assign value of type …
#0  myla_checker$Checker.check_stmt () at selfhost/checker.my:2561
#1  myla_checker$Checker.check_block () at selfhost/checker.my:2547
#2  myla_checker$Checker.check_function () at selfhost/checker.my:2756
#3  myla_checker$Checker.run_phases () at selfhost/checker.my:3179
#4  myla_checker$Checker.run_all () at selfhost/checker.my:3162
#5  myla_checker$build_checker_decls () at selfhost/checker.my:3221
#6  myla_emit_asm () at selfhost/gen_main.my:18
#7  myla_main () at selfhost/gen_main.my:48
#8  _start ()
```

(Line numbers are those of the tree at the time; addresses shortened.)

## What doesn't work yet

- **Variables.** gdb doesn't know Myla's locals or types yet. Every local has a fixed slot at a negative offset from `%rbp`; with `--keep-asm` you can find the slot in the `.s` file and read it with `x/gd $rbp-24`. Variable and type information is the next step of [[MYLA-66]].

## Other tools

- `myla run` reports runtime errors with their source position; reproduce there first when a native binary just exits with status 1 (native traps are silent: [[MYLA-17]]).
- `myla build --keep-asm` keeps the generated `.s` next to the binary; `myla parse` and `myla tokenize` dump the front end's view of a file.
- `readelf --debug-dump=decodedline ./binary` lists the line table that `-g` produced.
