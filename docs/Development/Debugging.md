# Debugging

[TOC]

## In VS Code

With the VS Code extension and gdb installed, `F5` on a `.my` file builds it with `myla build -g` and debugs it: breakpoints (conditions, hit counts, functions), stepping, the call stack, locals and arguments to expand, evaluation in the Debug Console and on hover, and a stop where a runtime error happens, with its message. The extension's own debug adapter drives gdb through its machine interface (D78, [[MYLA-99]]); how it works is on [[Architecture/Editor-tooling]], the launch attributes in the extension's README.

- No `launch.json` is needed: `F5` debugs the active file. With one, a configuration of type `myla` names the `program` (a `.my` file, or a binary built with `-g`), its `args`, `cwd`, `env`, a `stdin` file and `stopOnEntry`.
- The Variables view shows heap strings and lists inside structs, tuples and enums as values (`label: "two"`, `items: [4, 5]`); enums show the active variant's fields. The adapter lets gdb load the binary's pretty-printers (below), so a value's one-line summary shows them as values too (`Bag {items: [4, 5], label: "two"}`); the children don't depend on them.
- Expressions are gdb's (Rust syntax, as below); `-exec <command>` in the Debug Console runs any gdb command, e.g. `-exec info registers`.
- *Runtime errors* in the Breakpoints view (on by default) stops at `__panic` and shows the frame that failed; the `__panic` frame itself is greyed out.
- `"trace": true` in the configuration shows the adapter's MI conversation with gdb in the Debug Console.

The adapter also runs on its own, speaking DAP on stdin/stdout (`node vscode-extension/myla/out/debugAdapter.js` after `npm run build`), for other editors. An excerpt of a session from its integration test (`DAP_TRANSCRIPT=<file> npm test` writes the whole one; paths shortened):

```
-> {"command":"setBreakpoints","arguments":{"source":{"path":"…/debuggee.my"},"breakpoints":[{"line":39},{"line":20}]}}
<- {"command":"setBreakpoints","success":true,"body":{"breakpoints":[{"id":1,"verified":true,"line":39,…},{"id":2,"verified":true,"line":23,…}]}}
   … (a second setBreakpoints for lines 39 and 23 replaces them: ids 3 and 4)
-> {"command":"configurationDone"}
<- {"event":"stopped","body":{"reason":"breakpoint","threadId":1,"allThreadsStopped":true,"hitBreakpointIds":[3]}}
-> {"command":"variables","arguments":{"variablesReference":3}}
<- {"body":{"variables":[{"name":"bag","value":"Bag {items: [4, 5], label: \"two\"}","type":"Bag","variablesReference":5},
                         {"name":"t","value":"(7, true)",…},{"name":"s","value":"Shape::Circle(Point {x: 1, y: 2}, 5)",…},
                         {"name":"xs","value":"[1, -2, 3]",…},{"name":"name","value":"\"héllo\"",…},{"name":"origin","value":"Point {x: 1, y: 2}",…}]}}
-> {"command":"variables","arguments":{"variablesReference":5}}
<- {"body":{"variables":[{"name":"items","value":"[4, 5]","type":"*mut [int32]","evaluateName":"bag.items",…},
                         {"name":"label","value":"\"two\"","type":"*mut str","evaluateName":"bag.label",…}]}}
-> {"command":"evaluate","arguments":{"expression":"xs[1] * 10","frameId":1,"context":"repl"}}
<- {"body":{"result":"-20","type":"long","variablesReference":0}}
-> {"command":"stepIn","arguments":{"threadId":1}}
<- {"event":"stopped","body":{"reason":"breakpoint","threadId":1,"allThreadsStopped":true,"hitBreakpointIds":[4]}}
```

and a runtime error (`debuggee.my panic`):

```
<- {"event":"stopped","body":{"reason":"exception","description":"Runtime error: division by zero","text":"division by zero",…}}
-> {"command":"stackTrace","arguments":{"threadId":1,"startFrame":0,"levels":20}}
<- {"body":{"stackFrames":[{"name":"__panic","line":0,"presentationHint":"subtle",…},
                           {"name":"ratio","source":{"name":"debuggee.my",…},"line":29,"column":1,"presentationHint":"normal",…},
                           {"name":"main",…,"line":46,…},{"name":"_start",…,"presentationHint":"subtle"}],"totalFrames":4}}
-> {"command":"continue","arguments":{"threadId":1}}
<- {"event":"output","body":{"category":"stderr","output":"runtime error: division by zero\n  --> …/debuggee.my:29:14\n"}}
<- {"event":"exited","body":{"exitCode":1}}
<- {"event":"terminated"}
```

## gdb on native binaries

Build with `-g` to get DWARF debug information: a line table ([[MYLA-71]]), the parameters and variables of every function with their types, the functions' result types, and pretty-printers for gdb ([[MYLA-66]]):

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
Run till exit from #0  myla_manhattan (a=..., b=...) at structs.my:16
0x00000000004015fa in myla_main () at structs.my:25
25	    print(manhattan(origin, here))      // 7
Value returned is $2 = 7
(gdb) next
7
28	    var moved = here
(gdb) next
29	    moved.x = 100
(gdb) next
30	    print(moved.x)                      // 100
(gdb) print moved
$3 = Point {x: 100, y: 4}
(gdb) print here
$4 = Point {x: 3, y: 4}
```

- Functions are named `myla_<name>` (`myla_main`, `myla_Point.len` for methods, `myla_geometry$area` for a function from module `geometry`, `myla___lambda_3` for lambdas, `myla_first__6.int32` for a generic instantiation, see [[Architecture/Monomorphization]]; the self-hosted backend names lambdas `myla_<function>__lam<n>`). `break myla_main`, `break myla_Point.len` and `break myla_geometry$area` work as written; quote a generic instance: `break 'myla_first__6.int32'`. gdb shows it as `myla_first.6.int32` in frames.
- Every statement and every expression-bodied match arm starts a line entry. Runtime helpers (`__alloc`, `__print_int`, …) have no source line; `step` into them shows assembly, `finish` gets you out.
- `-g` changes nothing else: the binary behaves exactly like one built without it, and its code is the same apart from labels (`tests/burn/test_debug_info.py`, `tests/unit/test_compiler.py`).
- `finish` prints the value a function returns (`Value returned is $2 = 7`): every function's debug information has its result type. An aggregate comes back through the hidden result pointer the function returns in `%rax`, so gdb shows a pointer to it (`(*mut Bag) 0x7ffe…`, `print *$` shows the value), or with the pretty-printers the value itself. A `float32`/`float64` result is in `%rax` too, where gdb's x86-64 rules expect `%xmm0`, so a float function has no result type and `finish` prints nothing: `print/f $rax` reads the double.

## Pretty-printers

A `-g` binary carries gdb pretty-printers for Myla values (D82): [[src/myla/debug/myla_gdb.py]], embedded by both compilers as an inline Python script in the binary's `.debug_gdb_scripts` section. They print what the DWARF types alone can't (see Variables below): a `str`, list, builder or map inside a struct, tuple, enum, list or map as its value instead of a pointer to its cell, a map as `{key: value, …}`, a boxed (recursive) enum inside an aggregate as its value, and a `float32` field or element as a float:

```
(gdb) info locals
nested = [[1, 2], [3]]
tree = Tree::Node(Tree::Leaf(1), Tree::Leaf(2))
fs = [0.100000001, 0.25]
pair = (1.5, "p")
names = {1: "one"}
m = {"x": 1}
words = ["a", "b"]
bag = Bag {items: [4, 5], label: "two", ratio: 0.100000001, tags: {"k": 4}}
(gdb) print *words[1]
$1 = "b"
(gdb) print/r *words[1]
$2 = str {len: 1, bytes: [98 'b']}
```

gdb runs a script embedded in a binary only from a path its `auto-load safe-path` allows, which by default (`$debugdir:$datadir/auto-load`) excludes your programs. Without permission gdb says so when it loads the program (`warning: File "…/prog" auto-loading has been declined by your 'auto-load safe-path'…`) and prints pointers to cells as before. To allow it:

- for one session: `gdb -iex 'add-auto-load-safe-path ./prog' ./prog` (`-iex` runs before the program is loaded; a directory allows everything below it);
- for good: the line `add-auto-load-safe-path ~/src/myproject` in `~/.config/gdb/gdbinit` (or `~/.gdbinit`); `set auto-load safe-path /` trusts every file, which gdb's warning also offers;
- or load the printers by hand, for any `-g` binary, without the permission: `source src/myla/debug/myla_gdb.py` (or `gdb -x …/myla_gdb.py ./prog`).

`info auto-load python-scripts` shows whether `myla-printers` was loaded, `info pretty-printer` lists `myla` among the global printers, `print/r x` prints one value without them, and `disable pretty-printer global myla` turns them off. They need a gdb built with Python (most distributions' is). A map prints in the order of its slots, the order `for k in m` visits them; long lists and maps stop after `print elements` entries (200 by default). The VS Code debugger lets gdb load them for the program it debugs.

## Variables

`info args`, `info locals`, `print` and the frame line show parameters (`self` included), locals, loop variables, match bindings, destructured names and, in a lambda, its parameters and captured variables. Each local is visible from the statement after its declaration to the end of its block, so a shadowed name shows the innermost binding (`info locals` lists inner blocks first) and a name not declared yet is unknown. The debug information says the program is Rust: gdb's Rust rules print values the way Myla writes them, and expressions (`print xs[1] * 10`, `print p.x + 1`) use a syntax close to Myla's. From `tests/burn/test_debug_info.py` (both backends print this), without the pretty-printers:

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
$3 = [str: int32] {len: 1, cap: 8, slots: [slot {state: 0, key: 0x0, value: 0}, …, slot {state: 1, key: 0x406a30, value: 1}, …]}
```

and with them `m = {"a": 1}`, `words = ["ab", "c"]`, `print *words[1]` gives `"c"`.

| Value | gdb shows |
| --- | --- |
| integers, `bool`, `char`, floats | the value: `-8`, `65535`, `true`, `233 'é'` (`'\xe9'` without a UTF-8 locale), `2.5`; a `float32` variable as a float (`0.100000001`) |
| `str`, `StringBuilder` variable | the text: `"hello"` |
| list variable | its elements: `[1, -2, 3]`; `print xs[1]` indexes, out-of-range indexes are refused |
| struct, tuple, enum | `Point {x: 3, y: 1.5}`, `(7, true)`, `Shape::Circle(…)`, `Option<int32>::Some(4)` (gdb writes `::` for Myla's `.`) |
| function value | its code and environment pointers, with the code's symbol |
| map variable; a `str`, list, builder or map inside a struct, tuple, enum, list or map; a boxed (recursive) enum inside one | with the pretty-printers the value (`"c"`, `[4, 5]`, `{"k": 4}`, `Tree::Leaf(1)`); without them a pointer: `print *x` shows the cell (`len`, `cap`, the bytes, `items`, or a map's `slots` with their `state`, 1 for occupied), and fields are reached through it: `print self.decls.items[0]`, `print self.decls.len` |
| a `float32` inside a struct, tuple, enum or list | with the pretty-printers a float (`0.100000001`); without them the double it is kept as (`0.10000000149011612`) |

`set var x = …` changes a variable; a signed integer is described as its whole 8-byte slot, so a negative value is stored sign-extended as the program expects.

How it works: the compiler writes `.debug_info` and `.debug_abbrev` itself, as assembler data ([[src/myla/compiler/dwarf.py]], [[selfhost/dwarf.my]] and the `dbg_*` methods of [[selfhost/codegen.my]]), and the assembler adds the line table from the `.loc` directives. Every slot has a fixed `%rbp` offset, so locations are `DW_OP_fbreg` offsets from the frame base `%rbp`; in a program with tasks, an async function's or lambda's variables live in its heap frame (D90), whose address is its argument word, so their locations are `DW_OP_fbreg 16; DW_OP_deref; DW_OP_plus_uconst` the slot's offset ([[MYLA-141]]), and the async normalizer's temporaries (`%aw1`, …) are left out like the compiler's own (`__…`); an aggregate parameter is reached through the address in its slot, a capture through the closure environment. A `str` variable is shown as a Rust `&str` whose two fields are computed from its cell (a composite location), a list variable as an array at its elements whose length is read from the cell's header (`DW_OP_push_object_address`). gdb gives array elements and fields only types of a fixed size (a dynamic one makes it fail an internal assertion), so heap values inside aggregates are pointers to descriptions of their cells, which the pretty-printers follow. See [[Architecture/Native-backend]], D75 and D82.

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

- **Heap values inside aggregates** are values only with the pretty-printers, which gdb loads only where `auto-load safe-path` allows (above); otherwise they are pointers to their cells (`print *x`), and a `float32` inside one is a double.
- **Float results**: `finish` prints nothing for a function returning a float (it is in `%rax`, gdb looks in `%xmm0`); `print/f $rax` right after `finish` shows it.
- **Calling Myla functions from gdb** (`print myla_add(2, 3)`) doesn't work: gdb passes arguments in registers, Myla on the stack.
- Expressions use gdb's Rust syntax: `print xs[i]` works, Myla's `len(xs)` doesn't (`print xs` shows the elements, `print x.len` a cell's length).

## Other tools

- `myla run` reports a runtime error with the values in the message and the source line; a native binary prints the message without the values and the position ([[MYLA-17]], [[MYLA-65]]).
- `myla build --keep-asm` keeps the generated `.s` next to the binary; `myla parse` and `myla tokenize` dump the front end's view of a file.
- `readelf --debug-dump=decodedline ./binary` lists the line table that `-g` produced, `readelf --debug-dump=info ./binary` the functions, variables and types.
