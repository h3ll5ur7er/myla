---
id: MYLA-66
title: Debugger support
type: feature
status: in-progress
priority: low
labels: [tooling, debugging, backend]
---
Debug Myla programs: breakpoints, stepping, inspecting variables.

## A cheap first step ([[MYLA-71]])

The assembler already supports line tables: emitting GAS `.file` and `.loc` directives before each statement's code (every AST node knows its line and column) gives DWARF line information, so `gdb ./prog` can set breakpoints on `file.my:12`, step line by line and show backtraces with Myla function names, with no other change. Labels are already `myla_<name>`.

## Further steps

- [x] Variable locations: every local has a fixed `%rbp` offset (one slot per local, never reused), which maps directly onto DWARF `DW_OP_fbreg` locations; types need DWARF type descriptions (structs, enums with tags, lists through their cell layout) or a gdb pretty-printer script. Done with DWARF types, no script (D75): see How.
- [ ] Interpreter-level debugging: a step/breakpoint hook in the tree-walking interpreter is easy and gives a debugger for `myla run`.
- [x] An editor front end: the Debug Adapter Protocol in the VS Code extension, next to the language server. Done in [[MYLA-99]] (D78): an own adapter over gdb's MI; `F5` builds the file with `-g` and debugs it, and the Variables view shows heap strings and lists inside aggregates as values.
- [x] Runtime traps print the failing source position ([[MYLA-65]]): not through the line table, which only `-g` builds have, but from a static position record each check passes to its trap, in every build (D75).
- [ ] Heap values inside aggregates and lists as values instead of pointers to their cells, and `float32` fields as floats: a gdb pretty-printer script (gdb can't give array elements or fields value-dependent types).
- [ ] Return values: a return type on each subprogram, so `finish` prints the value.
- [ ] The self-hosted compiler records `.` as the compilation directory: it needs a way to read the working directory (a primitive like those of [[MYLA-64]]).

## Done when

- [x] `myla build -g` emits line tables; `gdb` steps through `examples/structs.my` ([[MYLA-71]])
- [x] Locals visible in gdb for scalars and strings, in both backends (and lists, structs, tuples, enums, builders, maps as pointers, parameters, `self`, captures)

## How

**Variables in gdb.** [[src/myla/compiler/dwarf.py]] (the Python backend) and [[selfhost/dwarf.my]] with the `dbg_*` methods of [[selfhost/codegen.my]] (the self-hosted one) write `.debug_abbrev` and one compile unit in `.debug_info` as assembler data; the assembler still builds `.debug_line` from `.loc`, into a section the unit points at. The unit's language is Rust: gdb's Rust rules print `char`, `uint8`, structs, tuples, enums and arrays as Myla writes them, and its expressions are close to Myla's.

- The DIEs are streamed while a function is generated: a subprogram per function (its label, frame base `%rbp`), parameters and captures for the whole function, and for every other binding (`let`/`var`, destructuring, loop variables, match bindings) a lexical block that starts at a label after its value is stored and ends where its Myla scope closes. All bindings go through one hook (`_bind`/`_push_scope`/`_pop_scope` in Python, `bind`/`bind_param`/`open_scope`/`close_scope` in Myla), so shadowing and scopes are exact.
- Locations follow the scope entries: `DW_OP_fbreg off`, then `DW_OP_deref` for an aggregate passed by address, or the environment's address plus the capture's offset.
- Types: scalars at their real width (a signed integer as its whole sign-extended slot, so `set var` keeps it canonical; a `float32` variable converts the double it is kept as); structs, tuples, enums as Rust variant parts, function values; a `str`/builder variable is a Rust `&str` made of two computed pieces; a list variable an array at its elements, its count read from the cell header through `DW_OP_push_object_address`. Inside aggregates and lists, heap values are pointers to cell descriptions: a value-dependent type there makes gdb fail an internal assertion (tried with `DW_AT_data_location`).
- Generic instances are named as in Myla (`Option<int32>`): the monomorphizer records `type_display_names`, the self-hosted backend uses the checker's `type_name`.
- Without `-g` nothing changes; with it the code is the same apart from labels. Match-statement arms with an expression body now get a line entry in the Python backend too, as in the self-hosted one.

**Runtime-error positions** ([[MYLA-65]]): each check jumps over `leaq .LposN(%rip), %rsi; call __trap_x`, where `.LposN` is `[file str][line:4][col:4]` in `.rodata`; `__panic` prints `runtime error: <message>` and `  --> file:line:col`. The `call` leaves a return address, so under gdb `break __panic` + `bt` shows the Myla frame (before: `?? ()`). Files are named as the compiling CLI names them in diagnostics. Found on the way: the Python interpreter named the caller's file for an error in an imported module's method, and the self-hosted interpreter ignored `m[k].f = v` for a missing key; both fixed.

## Evidence

- `tests/burn/test_debug_info.py`: `GdbVariables` runs against the Python backend and the self-hosted one (`gen_main -g`): scalars of every kind (`small = -8`, `huge = 18446744073709551615`, `f = 0.100000001`, `ch = 233 'é'`), values while stepping, shadowing (`x = 2` then `x = 1`) and names out of scope, `name = "hello"`, `xs = [1, -2, 3]`, `cs = [97 'a', 98 'b']`, `p = Point {x: 3, y: 1.5}`, `t = (7, true)`, `s = Shape::Circle(Point {x: 3, y: 1.5}, 2)`, `o = Option<int32>::Some(4)`, `sb = "built"`, `print *words[1]`, `print *m`, `info args` with a struct and an enum passed by address, `self`, a lambda's parameter and capture, and `set var c = -3` read back by the program as -3 (before the signed-slot rule it saw 4294967293). Plus the line-table tests with arguments in frames (`myla_add (a=2, b=3)`) and the abbreviation tables of both backends compared. Before the change, 12 of the 18 tests the file then had failed; after it, all 21 pass.
- `tests/unit/test_compiler.py`: no debug sections without `-g`; subprograms and variables are described; a block label follows a local's store; with the debug labels and directives removed, the code is the same as without `-g`.
- Every example built by both backends with and without `-g` prints the same; gdb (`maint expand-symtabs`) and readelf read every `-g` binary without a complaint; a gdb script stopping in every function of every example and printing `info args`/`info locals`/`bt` reports no error, and so do 3,000 function entries and 3,000 `step`s through the self-hosted compiler built with `-g` by either backend.
- Without `-g`, the Python backend's assembly of all 31 examples, and the self-hosted backend's of all examples and of the compiler itself, is byte-identical to before (the runtime-error commit).
- The compiler built with `-g`: 2,236,168 bytes instead of 1,965,000 (`.debug_info` 215 KB).
- A real session on the compiler: [[Development/Debugging]].
