---
id: MYLA-255
title: Function parameters with default values
type: feature
status: done
priority: low
labels: [language, ergonomics, design]
---
The owner's idea (2026-11-03), for after the runtime's port ([[MYLA-162]]): a parameter with a default value, which a call may leave out.

```myla
fun connect(host: str, port: int = 80, retries: int = 3) -> Conn { … }

connect("example.org")             // port 80, retries 3
connect("example.org", 8080)       // retries 3
```

Questions for the design round (a decision before the implementation):
- **Which arguments can be left out:** only trailing ones (positional, as C++ and Python without keywords), or with named arguments too (`connect("x", retries: 5)`, as Swift and Kotlin)? Myla has no named arguments yet; adding them is a decision of its own and changes what a call looks like everywhere.
- **What a default may be:** a constant expression only (simplest, and the same value every call), or any expression evaluated at each call, in the callee's scope (seeing earlier parameters?) or the caller's? Python's evaluated-once mutable default is the trap to avoid; Myla's values are immutable, which removes most of it.
- **Function values and types:** does `(str, int) -> Conn` hold `connect`, and can a call through a function value leave arguments out? (Swift: no, defaults belong to the declaration.) Partial application (`connect(_, 8080)`) and `|>` must stay unambiguous.
- **Methods, traits and generics:** may a trait's method declare defaults; must an `impl` repeat them; can a default mention a type parameter?
- **Lowering:** the caller fills in the missing arguments, so the callee and its calling convention (D119) stay as they are; `become` (D87) and the stack-word rule count the filled-in arguments.
- **Interplay:** overloads don't exist in Myla, so no ambiguity there; the checker's messages for a wrong number of arguments name the defaults; the LSP's signature help shows them.

- [x] Design round and a decision (D136); the examples and errors on [[Language/Functions-and-closures]] come with the implementation
- [x] Parser, checker, lowering, interpreter; error-corpus examples; the tree-sitter grammar and the editor

## Decided (2026-11-05): D136

The owner chose the recommendation:
- **Which parameters:** trailing ones only, and no named arguments for now.
- **What a default may be:** any expression that doesn't refer to other parameters, evaluated by the caller at each call.
- **Function types:** defaults belong to the declaration, not the function type.

## Built (2026-11-05)

- **The AST and the parser:** `Param` has a `default` ([[selfhost/ast.my]]). The parser reads `= expression` after a function's or method's parameter type; a lambda's parameters take none.
- **The loader** qualifies a default's names in its declaration's module ([[selfhost/loader.my]], `params`).
- **The checker** ([[selfhost/checker.my]]):
  - `check_defaults`: only trailing parameters have defaults; each is of its parameter's type and is checked before any parameter is in scope. A parameter whose type mentions a type parameter can't have one, as the caller couldn't evaluate it.
  - `call_arity` takes the place of the three exact argument counts: a call may leave out the defaults, and the ones it leaves out are recorded in `call_defaults`.
  - `become`'s word rule counts the defaults (D131).
  - A trait's methods can't have defaults.
- **Filling them in:** `fill_defaults` runs once the program is checked and appends the recorded defaults to each call, in the declarations, the signatures and the method bodies; a default that calls a function with defaults is filled too. The interpreter, the lowering and every backend needed no change.
- **Function values and partial application** take every argument, as the defaults belong to the declaration.
- **Docs and grammar:** [[Language/Functions-and-closures]] ("Default values"), the grammar's `param` rule, the regenerated tree-sitter grammar.

Evidence:
- **`tests/burn/test_default_params.py`,** written first. Its program covers:
  - defaults left out and given;
  - a default that's an expression over a constant;
  - a method's default;
  - `become` leaving one out;
  - a default calling a function with defaults;
  - a function value;
  - `|>`;
  - `async let`;
  - `await` of an async function.

  It prints the same in the interpreter and natively, and under aarch64 (qemu) and wasm32 (Node), checked by hand. Its eight error cases give their messages, and a `>=` split before a default parses.
- **Error corpus:** two new files.
- **Parser gate:** its case `split_ge_in_a_parameter`, a syntax error before D136, is now valid code and moved to test_default_params.
- **Suites:** the parser, checker, interpreter and CLI gates, test_lsp, test_examples_tests, test_grammar, test_doc_blocks and test_error_corpus pass.
- The fixed point is reached and the seeds updated.
