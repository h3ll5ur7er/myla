---
id: MYLA-4
title: Python backend crashes the self-hosted checker on an unknown parameter type
type: bug
status: todo
priority: high
labels: [native-backend, selfhost, tests]
---
`tests/burn/test_selfhost_checker.py::test_corpus_check_parity` fails 5 subtests: `type_generic_arity_mismatch`, `type_generic_missing_args`, `type_self_outside_trait`, `type_type_args_on_non_generic`, `type_unknown_type` (all in `examples/errors/`). This is the only red test in the suite.

## Steps to reproduce

```bash
python3 myla.py build selfhost/check_main.my -o /tmp/check
/tmp/check examples/errors/type_unknown_type.my   # segfault, exit 139
```

A function whose *parameter* annotation names an unknown type (`fun f(x: Nope)`) is enough; a bad return type or `let` annotation is fine.

## Expected

`err 2 10 type`, which is what `python3 myla.py run selfhost/check_main.my …` (the interpreter) and the same program compiled by the self-hosted stage3 print.

## Actual

SIGSEGV. dmesg: `segfault at fffffffffffffff8`, instruction `dec qword [rdi-8]`: a refcount decrement on a null cell pointer, most likely the drop of a heap owner that was never initialized on an early-return (`?`) path.

## Done when

- [ ] Root cause found and fixed in [[src/myla/compiler/codegen_x86.py]]
- [ ] A minimal parity test reproduces it
- [ ] `test_selfhost_checker.py` is green
