---
id: MYLA-221
title: "Methods on builtin types; the free collection functions deprecated"
type: feature
status: in-progress
priority: medium
labels: [language, builtins, stdlib]
---
D103 ([[MYLA-204]]): `impl` blocks on builtin types are allowed, the builtin collection and string functions become methods, the free forms warn until the repository has moved, then go.

- [x] The list: every builtin function on lists, maps, strings and chars with its method name and whether it takes `var self` (`push`, `insert`, `remove`, `set`, …)
- [ ] `impl [T]`, `impl Map<K, V>`, `impl str`, `impl char` and the numeric types in the checker; method lookup on builtin receivers; mutating methods need a `var` place, with the same diagnostics as `var self` methods today
- [ ] The free forms give a deprecation warning that names the method
- [x] The repository's code moved (examples, `tools/`, the standard library; `selfhost/` after a seed update, [[MYLA-218]])
- [ ] The free forms removed; [[Language]] pages, the skill, `AGENTS.md` ("`push(xs, v)`") and the grammar updated

Before the standard library round ([[MYLA-211]]), which builds on it. Order: after [[MYLA-219]] this touches only the self-hosted toolchain (checker, interpreter, lowering) and the grammar; done before it, the Python checker and interpreter need it too. Using it in `selfhost/` itself needs a seed that knows it ([[MYLA-218]]).

## Evidence

- **Step 1: the builtin functions as methods.**
  - **The list.** Builtins that take a receiver, and so become methods (`builtin_method` in [[selfhost/checker.my]]):
    - `len`: lists, maps, strings, `StringBuilder`;
    - `push`, `pop`: lists (`var`);
    - `contains`, `keys`, `remove`: maps (`remove`: `var`);
    - `chars`: strings;
    - `append`, `append_byte` (`var`), `build`: `StringBuilder`.

    `print`, `format`, `assert`, `panic`, `unreachable` and `StringBuilder()` have no receiver and stay functions. `insert` and `set` don't exist as builtins.
  - **How.** The checker, the interpreter and the lowering each treat `recv.m(args)` as the builtin call `m(recv, args)` when `recv`'s type is a builtin one, `m` is in the list, and the type has no method `m` of its own. The builtin's checks (a `var` place, the types) and its implementation apply unchanged. A local named like the method doesn't hide it (`builtin_as_method`). `impl int`, `impl str` and the like already worked.
  - **Test first.** `tests/burn/test_builtin_methods.py`:
    - every method;
    - mutation through a field (`self.items.push(x)` in a `var self` method) and a list element (`grid[0].push(9)`);
    - `let chars = s.chars()`, a type's own `len` coming first, the function forms still working;
    - errors: `push` on a `let`, a method the type lacks, a wrong arity.

    Before the change `xs.push(3)` was "type '[int32]' has no method 'push'"; now the output is the same in the interpreter and natively.
  - **Docs.** [[Language/Collections-and-strings]] (a section), `AGENTS.md` and the myla skill.
- **Step 2: the compiler, the tools and the standard library use the methods.**
  - A rewriting script, working from the self-hosted lexer's tokens, turned 3,201 calls in `selfhost/`, `tools/` and `lib/std/` (51 files) into method calls: `f(a, rest)` becomes `a.f(rest)`, with `a` in parentheses unless it is a postfix chain.
  - Everything checks, the bootstrap reaches its byte-identical fixed point from the new seed, and the burn suite passes.
  - Skips rise from 19 to 41: the command-parity corpus of `test_selfhost_cli` compares the CLI on every file of `tools/` and `selfhost/` with the recorded Python CLI, and those files changed. They are the compiler's own code, covered by the bootstrap and the tools' tests.
  - The examples, the error corpus, the docs and the test programs in `tests/burn/` still use the function forms, which work. Their recordings are keyed by their text, so moving them needs the recordings to survive it (step 3).
- **Step 3: the examples, the docs and the test programs use the methods.** [[MYLA-240]] made the recordings survive the rewrite, then moved them with the same script (`scripts/to_methods.py`): 59 files. Programs about the function form (its errors, a local shadowing it, "the function forms still work") keep it until step 4 decides what becomes of them.

