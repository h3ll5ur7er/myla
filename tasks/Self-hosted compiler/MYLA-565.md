---
id: MYLA-565
title: "An invalid spec given to `x.format(spec)` on a builtin `T: Format` is reported at the call interpreted and in std.fmt natively"
type: bug
status: review
priority: low
labels: [interpreter, native, diagnostics, parity]
---
Found by round 6's checker lane ([[MYLA-544]], C8). `x.format(spec)` on `x: T` with `T: Format` at a builtin `T` formats by a spec known only when it runs, so an invalid one is a runtime error. Both runners say `invalid format spec 'q'` and exit 1, but at different places: natively inside std.fmt, where `fmt_int` panics; interpreted at the call, as the interpreter formats with its own copy of std.fmt and only reaches the program's when the program loads std.fmt (with `import std.fmt as fmt` the interpreter's report is native code's). D183 wants the interpreter's report from both.

```myla
fun show<T: Format>(x: T, spec: str) -> str { return x.format(spec) }
fun main() {
    print(show(5, "q"))
}
```

```
$ myla run f1.my
runtime error: invalid format spec 'q'
  --> f1.my:1:62
$ myla build f1.my -o f1 && ./f1
runtime error: invalid format spec 'q'
  --> <myla>/std/fmt.my:209:28
```

The call is the better place (the spec is the caller's mistake, as a hole's invalid spec is a type error at the hole).

- [x] One place on every runner, the call, as D183 asks: native code checks the spec at the call (`std.fmt.parse_spec`) before `fmt_int`, `fmt_float` or `fmt_text`, or the lowering passes the call's position
- [x] A test in `tests/burn/test_compiler_parity.py`'s `RUNTIME_ERRORS`

## What was built

- **Native code** ([[selfhost/lower.my]]'s `builtin_format`, given the call's position): the spec is checked at the call by std.fmt's new `spec_error(s)` (why `s` isn't a spec, `""` when it is: `parse_spec`'s error), and one that isn't is a panic there, before `fmt_int`, `fmt_float` or `fmt_text` (`std$fmt$spec_error` is in `backend_std_functions`, [[selfhost/checker.my]]).
- **The interpreter** ([[selfhost/interp.my]]): a spec that isn't one is reported at the call with `parse_spec`'s text, always; it no longer calls the program's std.fmt when the program loads it (which put the report inside std.fmt, as native code's was). Its text was `invalid format spec '…'` without the reason a width or precision above 1,000,000 has (`invalid format spec '9999999': a width above 1000000`); it is native code's now.
- [[Language/Collections-and-strings]] (a spec checked when the program runs), [[Language/Standard-library/Fmt]] (`spec_error`).

## Evidence

- **Failing first**: the new `RUNTIME_ERRORS` programs (`runtime_spec_of_an_int`, `…_of_a_float`, `…_of_text`, `…_with_std_fmt`) and `test_compiler_parity…test_a_runtime_spec_is_reported_at_the_call` against the base: natively `--> …/lib/std/fmt.my:209:28` (and `:150:28`, `:249:28`), interpreted with `import std.fmt` `--> …/lib/std/fmt.my:150:28`, and interpreted `invalid format spec '9999999'` against native code's `…: a width above 1000000`: 7 failures. Now both pass, every report at `main.my:1:62` (`:3:62` with the import), and on aarch64 (qemu) and wasm32 (Node) too (`MYLA_TEST_TARGET`).
- A valid spec costs one more `parse_spec` a call natively; 4,000,000 `x.format(">7")` calls of an `int` and a `str` in 0.9 s, 11 MB resident (no leak of `spec_error`'s string), the same with `--checked`.
- `build/myla test lib/std/fmt.my --stdlib lib`: 36/36 interpreted, `--native`, `--target aarch64-linux`, `--target wasm32-wasi`; `build/myla test selfhost/lower.my` 150/150.
