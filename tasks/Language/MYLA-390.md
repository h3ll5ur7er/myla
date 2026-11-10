---
id: MYLA-390
title: "Small gaps from wave 4: for (k, v) in pairs, slicing bytes that aren't UTF-8"
type: improvement
status: done
priority: low
labels: [language, strings]
---
Found by the wave 4 lanes ([[MYLA-348]], [[MYLA-352]], [[MYLA-349]]).

- [x] `for (k, v) in pairs` doesn't parse ("expected loop variable name"); two lanes wrote `for kv in pairs { let (k, v) = kv }`. A tuple pattern in a `for` head (and maybe any irrefutable pattern), in the grammar, the checker and every runner
- [x] `s[a:b]` is "a slice bound inside a character" when `b` lands on a byte of the form `10xxxxxx` even where the bytes around it aren't a well-formed sequence. Strings are bytes (D164): decide whether the check should only refuse a bound inside a *well-formed* character, and say so on [[Language/Collections-and-strings]]. `std.xml` copies through `StringBuilder.append(s, a, b)` instead
- [x] `StringBuilder` has no `append_char`

## Decided (D174, 2026-11-09)

The owner accepted the recommendation: `s[a:b]` stays by bytes (D143), and a bound is refused only strictly inside a well-formed UTF-8 sequence. Built in the toolchain-fixes batch 3.

## What was built

- **`for` over a tuple of names.** `for (k, v) in e`, nested tuples and `_` (the irrefutable patterns a destructuring `let` takes; a variant pattern such as `Some(x)` isn't irrefutable and stays out). The parser ([[selfhost/parser.my]] `for_stmt`) gives the loop a hidden variable `%for<id>` and starts the body with `let (k, v) = %for<id>`, as the `if let`/`while let` rewrites do, so the checker, the interpreter's loops (sync and async), the lowering and the iterator rewrite ([[MYLA-380]]'s `while let`) take it unchanged, and a wrong shape is `let`'s error at the tuple (`cannot destructure non-tuple value of type 'int32'`, `tuple pattern expects 3 element(s), but value has 2`). Grammar ([[grammar/myla.ebnf]], [[Language/Grammar]]: `for_stmt = "for" ( IDENT | bind_tuple ) "in" …`), tree-sitter regenerated, [[Language/Statements#Loops]], [[Language/Standard-library/Map]], the skill.
- **D174's slice rule.** `std.slice`'s `str_whole` (which the interpreter calls and native code calls on every target) refuses a bound only when its byte is a continuation byte of a well-formed sequence: it looks back at most three bytes for the lead and measures the sequence as `s.chars()` decodes it (`seq_len`: no overlong form, no surrogate, nothing past U+10FFFF, not cut short). [[Language/Collections-and-strings]], [[Language/Standard-library/Slice]], [[Language/Standard-library/Str]], [[Language/Standard-library/Regex]], [[Language/Attributes-and-testing]], the skill.
- **The workarounds.** Removed: `std.xml`'s `piece()` (its four calls are slices now: a name ends before a byte that decodes to nothing, never inside a well-formed character). Kept, since they don't exist only for this: `std.term`'s `part()` (an unknown key `ESC O <byte>` takes three bytes, which may cut a well-formed character; its comment says "a character cut or not"), `std.http`'s `part()` (a status code's three bytes and the tests' pieces of a wire cut anywhere, and it returns the string itself when whole), `std.net`'s `tail_of()` (a datagram's bytes after its 19-byte sender record, whose last byte, the port's low byte, may lead a sequence the data's first byte continues). `dns_name`'s `sb.append(n, start, end)` builds its output in a builder anyway: not a workaround.
- **`StringBuilder.append_char(c)`.** A builtin method like `append_byte`: the checker takes a `char` on a `var` builder, the interpreter appends the character's UTF-8 text, native code calls std.rt's new `sb_append_char` (pure Myla over `sb_append_byte`, so no seed staging). [[Language/Collections-and-strings]], [[Language/Standard-library]], the skill.

## Evidence

- Before: `for (k, v) in pairs` was "expected loop variable name"; `s[1:3]` of a string `41 80 81 …` was `runtime error: a slice bound inside a character` (interpreted and native); `sb.append_char('é')` didn't exist.
- After, each on x86-64, aarch64 (`MYLA_TEST_TARGET=aarch64-linux`) and wasm32 (`MYLA_TEST_TARGET=wasm32-wasi`): the parity programs `for_tuple_patterns` (lists, `m.items()`, a user iterator, `iter.enumerate()`, nested tuples, `_`, nested loops with `break`/`continue`, an async loop with an `await`) and `append_char` (one to four bytes, a struct's field, a list's element, a copy, 1,000 appends); `test_bytes_that_are_no_character` and the runtime-error case `inside_a_character_among_bytes` in [[tests/burn/test_slices.py]]; `std.xml`'s 97 cases interpreted, `--native` and `--target aarch64-linux`. The error corpus: `type_for_tuple_over_non_tuples`, `type_append_char_of_a_byte`. std.slice's new `#test` cases (`seq_len`, `at_boundary`).
- The bootstrap reaches its fixed point.
- The suites, at the batch's last commit: `scripts/test.sh fast` 714 tests, all pass but `test_embedded_std` (the embedded library isn't committed, by the batch's rules: the seed commit regenerates it) and once `test_time`'s `test_an_async_read_lets_the_other_tasks_run` under the load of the run (it passes alone, three times out of three); `test_compiler_parity`, `test_selfhost_cases`, `test_error_corpus`, `test_selfhost_checker`, `test_lsp`, `test_grammar` (with the tree-sitter CLI), `test_selfhost_codegen`, `test_selfhost_interp`, `test_xml`, `test_http`, `test_aarch64`, `test_wasm`, `test_native_runtime`: 808 tests OK; `scripts/test-target.py aarch64-linux` and `wasm32-wasi`: 21 of 21 suites each.

## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]], with a follow-up in [[MYLA-417]]: no hint towards `m.items()` for `for (k, v) in m`.
