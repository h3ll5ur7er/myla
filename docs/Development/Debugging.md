# Debugging

[TOC]

## gdb on native binaries

Build with `-g` to get DWARF debug information: a line table ([[MYLA-71]]) and the parameters and variables of every function with their types ([[MYLA-66]]):

```bash
python3 myla.py build examples/structs.my -o structs -g
gdb ./structs
```

Then break on Myla source lines, step line by line, read backtraces and look at variables. A real session on `examples/structs.my` (gdb prints absolute paths in frames; shortened here):

```
(gdb) break structs.my:16
Breakpoint 1 at 0x401723: file structs.my, line 16.
(gdb) run
3
4

Breakpoint 1, myla_manhattan (a=..., b=...) at structs.my:16
16	    return dx + dy
(gdb) bt
#0  myla_manhattan (a=..., b=...) at structs.my:16
#1  0x00000000004015fa in myla_main () at structs.my:25
#2  0x0000000000401028 in _start ()
(gdb) info args
a = Point {x: 0, y: 0}
b = Point {x: 3, y: 4}
(gdb) info locals
dy = 4
dx = 3
(gdb) print a.x - b.x
$1 = -3
(gdb) up
#1  0x00000000004015fa in myla_main () at structs.my:25
25	    print(manhattan(origin, here))      // 7
(gdb) info locals
here = Point {x: 3, y: 4}
origin = Point {x: 0, y: 0}
(gdb) down
#0  myla_manhattan (a=..., b=...) at structs.my:16
16	    return dx + dy
(gdb) finish
0x00000000004015fa in myla_main () at structs.my:25
25	    print(manhattan(origin, here))      // 7
(gdb) next
7
28	    var moved = here
(gdb) next
29	    moved.x = 100
(gdb) next
30	    print(moved.x)                      // 100
(gdb) print moved
$2 = Point {x: 100, y: 4}
(gdb) print here
$3 = Point {x: 3, y: 4}
```

- Functions are named `myla_<name>` (`myla_main`, `myla_Point.len` for methods, `myla_geometry$area` for a function from module `geometry`, `myla___lambda_3` for lambdas, `myla_first__6.int32` for a generic instantiation, see [[Architecture/Monomorphization]]; the self-hosted backend names lambdas `myla_<function>__lam<n>`). `break myla_main`, `break myla_Point.len` and `break myla_geometry$area` work as written; quote a generic instance: `break 'myla_first__6.int32'`. gdb shows it as `myla_first.6.int32` in frames.
- Every statement and every expression-bodied match arm starts a line entry. Runtime helpers (`__alloc`, `__print_int`, …) have no source line; `step` into them shows assembly, `finish` gets you out.
- `-g` changes nothing else: the binary behaves exactly like one built without it, and its code is the same apart from labels (`tests/burn/test_debug_info.py`, `tests/unit/test_compiler.py`).

## Variables

`info args`, `info locals`, `print` and the frame line show parameters (`self` included), locals, loop variables, match bindings, destructured names and, in a lambda, its parameters and captured variables. Each local is visible from the statement after its declaration to the end of its block, so a shadowed name shows the innermost binding (`info locals` lists inner blocks first) and a name not declared yet is unknown. The debug information says the program is Rust: gdb's Rust rules print values the way Myla writes them, and expressions (`print xs[1] * 10`, `print p.x + 1`) use a syntax close to Myla's. From `tests/burn/test_debug_info.py` (both backends print this):

```
(gdb) info locals
m = 0x7fffb7e000f0
add_k = fn(int32) -> int32 {code_ptr: 0x4023f9 <myla___lambda_0>, env_ptr: 0x7fffb7e000d0}
k = 10
sb = "built"
o = Option<int32>::Some(4)
s = Shape::Circle(Point {x: 3, y: 1.5}, 2)
t = (7, true)
p = Point {x: 3, y: 1.5}
words = [0x4069d0, 0x4069f0]
cs = [97 'a', 98 'b']
xs = [1, -2, 3]
name = "hello"
(gdb) print *words[1]
$2 = str {len: 1, bytes: [99 'c']}
(gdb) print *m
$3 = [str: int32] {len: 1, cap: 8}
```

| Value | gdb shows |
| --- | --- |
| integers, `bool`, `char`, floats | the value: `-8`, `65535`, `true`, `233 'é'` (`'\xe9'` without a UTF-8 locale), `2.5`; a `float32` variable as a float (`0.100000001`) |
| `str`, `StringBuilder` variable | the text: `"hello"` |
| list variable | its elements: `[1, -2, 3]`; `print xs[1]` indexes, out-of-range indexes are refused |
| struct, tuple, enum | `Point {x: 3, y: 1.5}`, `(7, true)`, `Shape::Circle(…)`, `Option<int32>::Some(4)` (gdb writes `::` for Myla's `.`) |
| function value | its code and environment pointers, with the code's symbol |
| map variable; a `str`, list, builder or map inside a struct, tuple, enum or list; a boxed (recursive) enum inside one | a pointer: `print *x` shows the cell (`len`, `cap`, the bytes or `items`), and fields are reached through it: `print self.decls.items[0]`, `print self.decls.len` |
| a `float32` inside a struct, tuple, enum or list | the double it is kept as (`1.5`, `0.10000000149011612`) |

`set var x = …` changes a variable; a signed integer is described as its whole 8-byte slot, so a negative value is stored sign-extended as the program expects.

How it works: the compiler writes `.debug_info` and `.debug_abbrev` itself, as assembler data ([[src/myla/compiler/dwarf.py]], [[selfhost/dwarf.my]] and the `dbg_*` methods of [[selfhost/codegen.my]]), and the assembler adds the line table from the `.loc` directives. Every slot has a fixed `%rbp` offset, so locations are `DW_OP_fbreg` offsets from the frame base `%rbp`; an aggregate parameter is reached through the address in its slot, a capture through the closure environment. A `str` variable is shown as a Rust `&str` whose two fields are computed from its cell (a composite location), a list variable as an array at its elements whose length is read from the cell's header (`DW_OP_push_object_address`). gdb gives array elements and fields only types of a fixed size (a dynamic one makes it fail an internal assertion), so heap values inside aggregates are pointers to descriptions of their cells. See [[Architecture/Native-backend]] and D75.

## Runtime errors under gdb

A runtime error prints its position in every build (`runtime error: <message>` and `  --> file:line:col`, [[MYLA-65]]). Under gdb, `break __panic` stops at any of them; the trap is reached by a `call`, so the backtrace shows the Myla frame and line that failed, and with `-g` its variables:

```
$ ./divz
runtime error: division by zero
  --> examples/errors/runtime_div_zero.my:5:14
$ gdb -q -batch -ex 'break __panic' -ex run -ex bt -ex up -ex 'info args' ./divz
Breakpoint 1, 0x000000000040109d in __panic ()
#0  0x000000000040109d in __panic ()
#1  0x0000000000401594 in myla_ratio (a=7, b=0) at examples/errors/runtime_div_zero.my:5
#2  0x0000000000401564 in myla_main () at examples/errors/runtime_div_zero.my:9
#3  0x0000000000401028 in _start ()
#1  0x0000000000401594 in myla_ratio (a=7, b=0) at examples/errors/runtime_div_zero.my:5
5	    return a / b
a = 7
b = 0
```

Before, the trap was a jump: the backtrace stopped at `?? ()` and the frame had no variables.

## The self-hosted compiler

The self-hosted compiler emits the same debug information with `-g` (`gen_main <file.my> <stdlib_root> -g`, or `myla build … -g` with the self-hosted CLI). The loader knows which node ids belong to which file (`Loaded.spans`), so each module gets its own `.file` entry. Like the Python backend, it records the working directory as the compilation directory (`std.fs.current_dir`, [[MYLA-98]]), so gdb finds sources given by relative paths from anywhere. That makes the self-hosted compiler debuggable in its own source: build it with `-g` by the stage 3 compiler and break in the checker while it reports a type error:

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

(Line numbers are those of the tree at the time, before variables: frames now show their arguments, `check_stmt (self=..., s=...)`; addresses shortened.) Its variables are there too, here at the first line of `check_stmt` while it checks `examples/hello.my`:

```
(gdb) print s
$1 = ast$Stmt {id: 26, line: 4, col: 5, kind: 0x7ffef7e085c8}
(gdb) print *s.kind
$2 = ast$StmtKind::IfS(ast$Expr {id: 19, line: 4, col: 16, kind: 0x7ffef7e08228}, ast$Block {line: 4, col: 23, stmts: 0x7ffef7e08528}, Option<ast$ElseTail>::None)
(gdb) print self.decls.items[1].line
$3 = 2
```

## What doesn't work yet

- **Heap values inside aggregates** show as pointers to their cells (`print *x`), and a `float32` inside one as a double: a gdb pretty-printer script (Python) could show them as values, at the price of loading it.
- **Return values**: subprograms have no return type, so `finish` doesn't print the value returned.
- Expressions use gdb's Rust syntax: `print xs[i]` works, Myla's `len(xs)` doesn't (`print xs` shows the elements, `print x.len` a cell's length).

## Other tools

- `myla run` reports a runtime error with the values in the message and the source line; a native binary prints the message without the values and the position ([[MYLA-17]], [[MYLA-65]]).
- `myla build --keep-asm` keeps the generated `.s` next to the binary; `myla parse` and `myla tokenize` dump the front end's view of a file.
- `readelf --debug-dump=decodedline ./binary` lists the line table that `-g` produced, `readelf --debug-dump=info ./binary` the functions, variables and types.
