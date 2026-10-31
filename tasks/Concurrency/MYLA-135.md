---
id: MYLA-135
title: Concurrency in the language and both checkers
type: feature
status: done
priority: medium
labels: [concurrency, language, checker, selfhost]
---
D89, first step of [[MYLA-61]]: the syntax and the rules, on the Language pages and in both checkers (with the same errors).

- [x] The syntax by example on a new Language page, for review: `actor` declarations and methods, `async fun`, `await`, `async let`, task groups, `#main async fun main()`; keywords and grammar ([[Language/Concurrency]], [[Language/Grammar]], the tree-sitter grammar, the VS Code grammar, the LSP's keywords)
- [x] Lexers and parsers (Python and self-hosted), with the same canonical trees and syntax errors
- [x] The rules: where `await` may stand, calling async functions only from async code, actor isolation (state only through `self` in its own methods, every outside call awaited), `async let` not outliving its scope (structural: only async functions have child tasks, and lambdas can't await them)
- [x] The error corpus for each rule (`examples/errors/type_*async*`, `type_actor_*`, …) and snippets for the self-hosted checker's parity test
- [x] The interpreters and backends refuse concurrent programs at their first construct of concurrency until [[MYLA-136]] … [[MYLA-139]]

Left for [[MYLA-136]] (done since): `std.task` (groups), and sendability, which every value has today (D89 point 5): a check only once a kind of value can't be copied.

## Evidence

- Error corpus: 18 new entries (`type_actor_*`, `type_async_*`, `type_await_*`, `type_become_in_async`, `type_compose_async`, `type_lambda_awaits_child_task`, `type_lambda_captures_actor_self`, `type_partial_async`, `type_test_async`), each failing as its header says in the Python checker; before the change each was a parse error.
- Self-hosted checker parity (`tests.burn.test_selfhost_checker`): the corpus plus 16 new snippets (async method, function value and generic calls without `await`, `async let` mismatch, duplicate and without a result, actor fields assigned, read from another actor, partially applied and called from outside, async types, `await` of a synchronous call and in a synchronous lambda, a call of an async method on `self`) give the same errors, positions and ranges.
- Self-hosted parser parity (`tests.burn.test_selfhost_parser`): a program with every construct, and each of its 62 prefixes, gives the same canonical tree or errors; 8 new syntax-error snippets give the same messages.
- Compiling itself, the compiler runs 0.35% more instructions (2,560,870,027 → 2,569,733,873, both compiling the same sources) with the same output; user time is unchanged within noise (median 0.837 s → 0.829 s over 20 alternating runs). A first version, with an async flag in every function type, cost 0.49%: the flag made every `Type` value a word larger, so async function types are a `TAsync` wrapper instead; the actor table's lookups and the suspension check are gated on cheap tests.
- Unit 595, integration 2, burn 787 (5 skipped) and the extension's 54 tests pass; the bootstrap reaches its byte-identical fixed point (5,405,772 bytes).
