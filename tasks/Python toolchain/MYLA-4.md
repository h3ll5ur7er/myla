---
id: MYLA-4
title: Python backend crashes the self-hosted checker on an unknown parameter type
type: bug
status: review
priority: high
labels: [native-backend, selfhost, tests]
---
`tests/burn/test_selfhost_checker.py::test_corpus_check_parity` failed 5 subtests: `type_generic_arity_mismatch`, `type_generic_missing_args`, `type_self_outside_trait`, `type_type_args_on_non_generic`, `type_unknown_type` (all in `examples/errors/`). This was the only red test in the suite.

## Steps to reproduce

```bash
python3 myla.py build selfhost/check_main.my -o /tmp/check
/tmp/check examples/errors/type_unknown_type.my   # segfault, exit 139
```

A function whose *parameter* annotation names an unknown type (`fun f(x: Nope)`) is enough; a bad return type or `let` annotation is fine.

## Expected

`err 2 10 type`, which is what `python3 myla.py run selfhost/check_main.my …` (the interpreter) and the same program compiled by the self-hosted stage3 print.

## Root cause

Found with `myla build -g` ([[MYLA-71]]) and gdb: the crash is in `__drop_list_checker$Type`, called from [[selfhost/checker.my#L1024]]:

```myla
for p in fd.params { push(ps, self.param_type(p)?) }
```

The native `push` made the list unique, grew it and **bumped its length before evaluating the value**. When `?` returned early, `ps` kept a zeroed element, and dropping `ps` on the way out dereferenced a null box. The interpreter evaluates the value first. The same order problem was in `m[k] = v` (crash) and `append_byte` (a stray NUL byte), and it showed without `?` too: `push(xs, pop(xs) * 10)` lost the value, `m[2] = len(m) * 100` saw the new key, and through `var self` the caller saw the half-pushed element.

Two more bugs in the same code: `xs[i] = xs[i]` with a struct holding a list released the old value before copying the new one (use-after-free), and replacing an element of a list of maps or builders crashed the compiler (`_list_drop_name` was used for every element type).

## Fix

Every store into a container now stages the value first ([[Architecture/Native-backend]], "Stores into containers"): `_stage_value` evaluates it into a frame slot that owns one reference, then the container is found, unshared and grown, the old value released and the staged one moved in (`_commit_staged`). Until the commit an early return (a `?` in the key, the index or the container expression) releases the staged value and its temporaries. The self-hosted code generator had the same order bug (it was ported from the Python one) and got the same change.

- [x] Root cause found and fixed in [[src/myla/compiler/codegen_x86.py]] (and [[selfhost/codegen.my]])
- [x] Tests first, each seen failing: `try_inside_push_leaves_the_list_intact`, `try_inside_map_insert_leaves_the_map_intact`, `try_inside_append_byte_leaves_the_builder_intact`, `push_evaluates_its_value_before_the_list`, `assign_replaces_map_and_builder_elements` in `tests/burn/test_compiler_parity.py`; the stress test `test_try_after_a_staged_value_releases_it` (the arena ran out without the early-return release); the same programs through the self-hosted compiler in `test_selfhost_codegen.py` (3 failed before)
- [x] `test_selfhost_checker.py` is green; the whole burn suite passes (330 tests)
- [x] Bootstrap fixed point holds (4,465,925 bytes)

Not covered: a `?` inside a list or map literal leaks the half-built literal (the cell isn't visible to anyone, so nothing breaks); the self-hosted `?` releases nothing at all ([[MYLA-22]]).
