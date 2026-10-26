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

## What doesn't work yet

- **Variables.** gdb doesn't know Myla's locals or types yet. Every local has a fixed slot at a negative offset from `%rbp`; with `--keep-asm` you can find the slot in the `.s` file and read it with `x/gd $rbp-24`. Variable and type information is the next step of [[MYLA-66]].
- **The self-hosted compiler** doesn't emit line tables yet. Since [[MYLA-30]] every node has a position in its own module, so the remaining work is recording each declaration's file ([[MYLA-28]]).

## Other tools

- `myla run` reports runtime errors with their source position; reproduce there first when a native binary just exits with status 1 (native traps are silent: [[MYLA-17]]).
- `myla build --keep-asm` keeps the generated `.s` next to the binary; `myla parse` and `myla tokenize` dump the front end's view of a file.
- `readelf --debug-dump=decodedline ./binary` lists the line table that `-g` produced.
