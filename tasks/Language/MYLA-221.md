---
id: MYLA-221
title: "Methods on builtin types; the free collection functions deprecated"
type: feature
status: review
priority: medium
labels: [language, builtins, stdlib]
---
D103 ([[MYLA-204]]): `impl` blocks on builtin types are allowed, the builtin collection and string functions become methods, the free forms warn until the repository has moved, then go.

- [x] The list: every builtin function on lists, maps, strings and chars with its method name and whether it takes `var self` (`push`, `insert`, `remove`, `set`, …)
- [x] `impl [T]`, `impl Map<K, V>`, `impl str`, `impl char` and the numeric types in the checker; method lookup on builtin receivers
- [x] `var self` methods on builtin types (a list or a number is one word, so the method has to give it back to its caller's place on every way out: a convention of its own)
- [x] The free forms give a deprecation warning that names the method (2026-11-06; then gone, below)
- [x] The repository's code moved (examples, `tools/`, the standard library; `selfhost/` after a seed update, [[MYLA-218]])
- [x] The free forms removed; [[Language]] pages, the skill, `AGENTS.md` ("`push(xs, v)`") and the grammar updated (2026-11-06; the grammar had nothing to change: a free call is a call)

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


- **Step 4 (2026-11-05): impls on lists, maps, `char` and the float types.** The checker, the interpreter and the code generator key them as `char`, `float64`/`float32`, `__list` and `__map` (names no program can declare), so a list's methods are those of every list, as a generic struct's are of every instance; `impl<T> [T]` and `impl<K, V> [K: V]` bind their parameters from the receiver. A concrete `impl [int]`'s method on a `[str]` is `method 'total' is for '[int32]', not '[str]'`. `var self` ones stay refused: natively the receiver would have to go back to its caller's place on every way out. [[tests/burn/test_builtin_impls.py]], and the same program on aarch64 and wasm32; `test_selfhost_checker`'s `impl_on_list` and `generic_impl_on_builtin` went.
- **Step 5 (2026-11-06): the function forms went.**
  - First a warning naming the method (`'push(x, …)' is deprecated: call it as a method, 'x.push(…)'`), which found the last uses: the prelude's `get` (`contains(m, k)`), the concurrency stress programs and the scheduling-order program (rewritten with `scripts/to_methods.py`), and test programs built from string pieces the script can't rewrite (by hand, to exactly what it writes, so the recorded answers' aliases from [[MYLA-240]] answer them). `local_closure_shadows_a_builtin`, whose locals of those names are closures, kept its local calls; its output is pinned (`PINNED`, which the self-hosted parity loops consult now too).
  - Then the error: `push(xs, v)` is "'push' is a method: call it as 'x.push(…)'" (`function_form` in [[selfhost/checker.my]]), with `scripts/to_methods.py` in the help. The names stay reserved (a program can't declare `fun push`), and a local closure of the name is still called as one; freeing them for a program's own functions would need the interpreter's and the lowering's call dispatch to change too.
  - The methods' arity errors no longer count the receiver (`push() takes 1 argument`, `chars() takes no arguments`, `append() takes 1 or 3 arguments`), and "did you mean" no longer suggests the method names for a call.
  - Tests: `test_builtin_methods.test_the_function_forms_are_gone` (seen failing first) and method-form cases for what the function forms' argument errors were (on a call, on a list, on a `let`, on an int); the eleven function-form snippets of `test_selfhost_checker` and two harvested ones went; the corpus files `type_pop_non_list.my` and `type_sb_build_non_builder.my` use the methods.
  - The recorded copies under `tests/burn/data/recorded_corpus/` keep the function forms: they are what was recorded, and only the lexer and parser gates read them.

## Proposal: `var self` on builtin types (2026-11-06; accepted by the owner the same day, option 1: D144)

**The problem.** A struct's `var self` method works because an aggregate is passed as a pointer to the caller's storage ([[Architecture/Native-backend]]): what the method writes lands in the caller's place. A list, a map, a string, a builder or a number is one word, passed by value, so a `var self` method on one changes only its own copy. (The interpreter writes the receiver back to its place generically; only native code lacks a way.)

**Options.**
1. **The receiver by address (recommended).** A `var self` receiver of a one-word type is passed as the address of the caller's place, as an aggregate already is; the method reads and writes `self` through it, and `self.push(v)` inside is the builtin on that place.
   - Every way out is covered with nothing to do: `return`, `?`, a panic, and a `become` (to another `var self` method of the same receiver, the address passes on; it points into a frame that outlives the call).
   - The call site needs the place's address. The places a `var self` struct method takes already have one (a `var`, a field, a list or map element after its copy-on-write), and the staging of an argument read from the receiver's variable (`xs.m(xs[0])`) applies as it is.
   - The cost: the receiver lives in memory across the call (not a register); for `x.inc()` on an `int` that's a store and a load.
   - It is IR only (loads and stores through a pointer parameter), so x86-64, aarch64 and wasm32 get it at once.
2. **Copy in, copy out.** The method gets the value and hands its final `self` back as a hidden second result, which the caller stores into the place. Every way out has to produce it: `?`'s early return, and a `become` to a function that isn't a `var self` method of the same receiver (which D87 must then refuse or wrap). More code at every exit, and a second calling convention for these methods.
3. **Keep refusing them.** A program then writes `xs = f(xs)` (Myla has no references, so there is no other way to change a caller's list from a function).

**Recommendation: 1.** It is the convention structs already use, so it needs no new rule in the language, only a new parameter kind in the lowering (a one-word value behind a pointer).

**Open points**, with my suggestions:
- An *async* `var self` method on a builtin type needs D99's write-back (the frame holds a copy, written to the place when the call completes), as a struct's does in an actor. I'd refuse these at first, with the error saying so, and add them when a program needs one.
- A `var self` method called on an element of a list that the method's arguments also read (`grid[0].m(grid[1])`) is already handled for structs by staging the argument, so nothing new.

**What it takes:** the checker drops the refusal; the lowering adds the pointer parameter and the place address at the call site; tests in the interpreter and natively on all three targets (a list `push`ing in a method, a counter on `int`, a method on a field and on a list element, `become` between two such methods). About a day.

## Step 6 (2026-11-06): `var self` on built-in types (D144)

- **The receiver by address**, as accepted: `recv_by_address` ([[selfhost/codegen.my]]) is a `var self` receiver of a type that isn't an aggregate. The lowering gives it a slot holding the address of the caller's place (typed `ptr`, the value's type kept as `by_addr_t`), so every place rooted at `self` (`self.push`, `self[i] = v`) works as for a struct, a read loads through the address (`read_var`), and `self = v` takes the member path (the old value dropped at the place, the new one stored). It is never an owned parameter (MYLA-127).
- **The call site** passes the place's address (`place`, each list on the way made unique). A list element narrower than a word (`[bool]`, `[int8]`, `[float32]`: stored at its size) goes in a cell of its own and is stored back after the call (`write_back`). A `become` may pass on only the receiver it was given; the checker already says so ("'become' can call the mutating method 'inc' only on 'self'").
- **The checker**: the refusal went; `self = v` is allowed in a built-in value's `var self` method only (`self_assignable`), still "cannot reassign 'self'" in a struct's or a read-only one; an async one is refused ("async 'var self' methods on built-in types are not supported yet"). The interpreter needed nothing: it writes the receiver back to its place.
- **Test first**: `test_builtin_impls.test_var_self_methods` (refused by the checker before; natively it then crashed with a segmentation fault), a program over a variable, a struct's field through its own `var self` method, list elements wide and narrow (`[int8]`, `[bool]`, `[float32]`), a map's value, `self = v` on a list, an `int`, a `str`, a `bool` and a `float32`, `?` leaving early with the receiver written, a `become` to itself, a copy made before the call unchanged. The same output in the interpreter, natively, on aarch64 (qemu) and on wasm32 (Node). `test_errors`: an async one, a call on a `let`, a `become` on a local, `self = v` in a struct's and in a read-only method.
- **Docs**: [[Language/Methods-and-traits]] (with an example whose output is checked), D144's row, the skill.
