---
id: MYLA-82
title: REPL written in Myla
type: feature
status: done
priority: low
labels: [repl, selfhost]
---
Part of the "everything in Myla" direction ([[Project/Roadmap]]). Supersedes [[MYLA-19]] (the Python `myla repl` stub). Built on the self-hosted interpreter ([[selfhost/interp.my]]; its performance is [[MYLA-74]]) and stdin ([[MYLA-78]]).

- [x] Line-by-line input; an open brace continues the input
- [x] Declarations accumulate; an expression prints its value
- [x] Errors are reported without ending the session

## How

`build/myla repl` ([[selfhost/repl.my]], dispatched from [[selfhost/main.my]]):

- A session is a program text: the declarations typed so far, then `fun __repl()` whose body holds the statement inputs, each in an `if true { … }` nested in the previous one's, so a later `let` may shadow an earlier name (a redeclaration in one block is an error in Myla).
- Each input is loaded with the text as an in-memory override (`load_program_with`) and checked as a whole, so imports, earlier declarations and earlier variables (with their types) are known. Then only the new input's statements run (`Interp.session_step`, new in [[selfhost/interp.my]]) in a scope that holds the session's variables; nothing typed before runs again, so output and side effects happen once.
- An input starting with a declaration keyword or an attribute joins the declarations; anything else is statements, and a final expression's value (if not unit) is printed as Myla source writes it (`"text"`, `'c'`, `P { x: 1 }`, `Some(1.5)`, `["a": 1]`, `[:]`, module prefixes dropped).
- An input goes on while it leaves a bracket open (counted on the compiler's tokens, so brackets in strings don't count).
- A lex, parse, type or runtime error is printed against the input's own lines (`--> <input>:3:12`, the source line and a caret), and the session stays as it was before the input (its variables rolled back). `exit(n)` ends the session with status n; the end of the input ends it with 0. Prompts (`myla> `, `...   `) go to stderr, so stdout carries only values and the program's output.
- The Python `myla repl` stub ([[MYLA-19]]) now points to `build/myla repl`.

## Evidence

- `tests/burn/test_selfhost_cli.py`, `TestRepl` (3 tests, failing before the command existed): a 28-line session (arithmetic, a multi-line function, a struct and assignment to its field, lists, maps, tuples, `Some(1.5)`, shadowing a variable with another type, `print`, an unknown name, an index out of range, a `for` loop, an import from `std.num`, an argument of the wrong type) prints exactly the 15 expected values and three errors, and exits 0; an error on the third line of a multi-line input is reported as `<input>:3`; `exit(4)` ends the session with status 4 and nothing after it runs.
- `repl.my`'s own `#test`s (bracket counting, declaration detection, value display, module prefixes, line counting); `tests/unit/test_cli_repl.py` for the Python pointer.
- About 15 ms per input with `std.json` imported, the same after 100 inputs (each input loads and checks the whole session).
