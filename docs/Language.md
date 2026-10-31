# Language

The reference for Myla as the Python toolchain implements it (version 1.0). The Python toolchain is the language's definition: where the self-hosted compiler behaves differently, the difference is a bug ([[Project/Known-issues]]).

[SUBPAGES]

## Design in brief

- **Statically typed, explicitly sized.** Integers are `int8` … `int64` and `uint8` … `uint64`, with `int` an alias for `int32`. There is no implicit conversion between numeric types; arithmetic wraps at the type's width. Use `as` to convert.
- **Value semantics.** Assignment, arguments and returns copy values: structs, tuples, enums, lists, maps and builders alike. Lists, maps and builders are reference-counted and copy-on-write, so copies are cheap.
- **Immutable by default.** `let` bindings can't be changed, and neither can anything inside them; `var` allows both.
- **Mostly statements.** `if` and loops are statements; `match` is an expression, and so are lambdas.
- **Newlines end statements.** A `;` may replace that line break to put several statements on one line (D61). Blocks use braces; indentation doesn't matter.
- **Errors as values.** `Option<T>` and `Result<T, E>` with the `?` operator; no exceptions. `panic`, `assert` and `unreachable` stop the program.
- **Everything checked before running.** The interpreter and the native backend both run only programs the checker accepted, and must agree on everything they print.

## Pages

| Page | Covers |
| --- | --- |
| [[Language/Lexical-structure]] | Comments, identifiers, keywords, literals, f-strings, newlines |
| [[Language/Types]] | Every built-in type, aliases, function types, `Option`/`Result` |
| [[Language/Expressions-and-operators]] | Precedence, operator typing, casts, `|>`, `>>`, `_`, `?`, evaluation order |
| [[Language/Statements]] | Bindings, assignment, control flow, scopes, return analysis, the entry point |
| [[Language/Structs-enums-and-match]] | Data types, patterns, exhaustiveness, recursive enums |
| [[Language/Functions-and-closures]] | Functions, function values, lambdas, captures, partial application |
| [[Language/Methods-and-traits]] | `impl`, receivers, traits, operator overloading, `#derive(Eq)`, bounds |
| [[Language/Generics]] | Generic functions and types, inference, monomorphization |
| [[Language/Collections-and-strings]] | Lists, maps, strings, `format`, `StringBuilder`, chars |
| [[Language/Modules]] | Imports, `pub`, packages, resolution rules |
| [[Language/Standard-library]] | `print` and the other built-in functions, `std.io`, `std.fs`, `std.process` |
| [[Language/Concurrency]] | Draft (D89): `async`/`await`, `async let`, task groups, actors |
| [[Language/Attributes-and-testing]] | `#main`, `#test`, `#derive`, `const`, `assert`/`panic`/`unreachable`, runtime errors |
| [[Language/Grammar]] | The grammar in EBNF |

The reasons behind each rule are recorded as numbered decisions (D1–D58) on [[Project/Decisions]].
