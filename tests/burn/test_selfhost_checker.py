"""Differential burn test for the self-hosted type checker (self-hosting v0.7).

`selfhost/checker.my` is the Myla-written type checker; `selfhost/check_main.my`
lexes + parses + type-checks a single-file program and prints the stable
accept/reject line (`ok`, else `err <line> <col> <span> type: <message>` for
each error, MYLA-65, D80). This test asserts that, for every single-file source
in the shared corpus and for every snippet of TYPE_ERRORS, those lines are
identical to the Python oracle's: the same verdict, errors in the same order,
positions, underlined ranges (MYLA-65) and messages (MYLA-28). That is the v0.7
checker-parity gate from docs/Development/Testing.md. The oracle's lines are
the retired Python checker's, recorded (`tests/burn/_golden.py`, MYLA-219).

As with the lexer/parser gates, the Myla checker runs as a *native binary*,
built by the self-hosted compiler (which also exercises the code generation of
the toolchain that built it); a host that cannot build one skips the gate.

The gate covers single-file programs that lex + parse cleanly and do not import
other modules (the self-hosted `check_main` has no module loader; it injects only
the `Option`/`Result` prelude, matching a no-import `myla check`). Files
that fail to lex/parse, or that use `import`, are excluded — they belong to the
lexer/parser gates or the runtime corpus, not the checker-parity gate.
"""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import tempfile
import unittest

from ._golden import NoGolden, golden
from ._mutants import mutants
from ._native import CAN_BUILD_NATIVE, SKIP_REASON
from ._tools import selfhost_tool

_REPO = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
)

# Programs the Python toolchain's unit tests expected to fail type checking,
# collected before it was retired (MYLA-219), then snippets for the messages they don't
# reach (named after the message).
_SNIPPETS = os.path.join(os.path.dirname(__file__), "data", "type_error_snippets.json")
def _main(*lines: str, before: str = "") -> str:
    """A program whose `main` body is `lines`, after the declarations `before`."""
    body = "".join(f"    {line}\n" for line in lines)
    return f"{before}fun main() {{\n{body}}}\n"


_S = "struct S { a: int }\n"
_SM = ("struct S { a: int }\nimpl S {\n    fun f(self, x: int) -> int {\n        return x\n    }\n"
       "    fun g<U>(self, x: U, y: U) -> int {\n        return 1\n    }\n"
       "    fun h<U>(self) -> int {\n        return 1\n    }\n}\n")
_E = "enum E { A, B }\nenum F { C }\n"
_P = "enum E { A(int) }\nenum G<T> { K(int) }\n"
TYPE_ERRORS: dict[str, str] = {
    "module_import": "import foo\nfun main() {}\n",
    "duplicate_trait": "trait T {\n    fun f(self) -> int\n}\ntrait T {\n    fun g(self) -> int\n}\nfun main() {}\n",
    "duplicate_field": "struct S { a: int, a: int }\nfun main() {}\n",
    "duplicate_variant": "enum E { A, A }\nfun main() {}\n",
    "type_param_shadows_builtin": "fun f<char>(x: char) {}\nfun main() {}\n",
    "type_param_shadows_int": "fun f<int>(x: int) {}\nfun main() {}\n",
    "duplicate_type_param": "fun f<T, T>(x: T) {}\nfun main() {}\n",
    "duplicate_trait_method": "trait T {\n    fun f(self) -> int\n    fun f(self) -> int\n}\nfun main() {}\n",
    "duplicate_trait_type_param": "trait T<A, A> {\n    fun f(self) -> A\n}\nfun main() {}\n",
    "trait_self_type_param": "trait T<Self> {\n    fun f(self) -> int\n}\nfun main() {}\n",
    "impl_extra_method": ("struct S { a: int }\ntrait T {\n    fun f(self) -> int\n}\nimpl T for S {\n"
                          "    fun f(self) -> int {\n        return 1\n    }\n    fun g(self) -> int {\n        return 2\n    }\n}\nfun main() {}\n"),
    "impl_receiver_mismatch": ("struct S { a: int }\ntrait T {\n    fun f(var self)\n}\nimpl T for S {\n"
                               "    fun f(self) {}\n}\nfun main() {}\n"),
    "derive_on_function": "#derive(Eq)\nfun f() {}\nfun main() {}\n",
    "derive_on_generic": "#derive(Eq)\nstruct B<T> { x: T }\nfun main() {}\n",
    "derive_and_impl": ("#derive(Eq)\nstruct S { a: int }\nimpl Eq for S {\n    fun eq(self, o: S) -> bool {\n"
                        "        return true\n    }\n}\nfun main() {}\n"),
    "derive_with_outputs": "#derive(Eq)[1]\nstruct S { a: int }\nfun main() {}\n",
    "derive_without_traits": "#derive\nstruct S { a: int }\nfun main() {}\n",
    "derive_non_name": "#derive(1)\nstruct S { a: int }\nfun main() {}\n",
    "derive_enum_payload": "#derive(Eq)\nenum E { A([int]) }\nfun main() {}\n",
    "generic_impl_order": ("struct P<A, B> { a: A, b: B }\nimpl<A, B> P<B, A> {\n    fun f(self) -> int {\n"
                           "        return 1\n    }\n}\nfun main() {}\n"),
    # (`impl<T> int` and `impl [int]` were two; since MYLA-221 lists and maps
    # take impls, generic ones too, and the message for `impl<T> int` says so:
    # test_builtin_impls)
    "self_type_args": "trait T {\n    fun f(self) -> Self<int>\n}\nfun main() {}\n",
    "type_param_args": "fun f<T>(x: T<int>) {}\nfun main() {}\n",
    "not_generic": "struct S { a: int }\nfun f(x: S<int>) {}\nfun main() {}\n",
    "const_value_type": "const X: int = \"s\"\nfun main() {}\n",
    "const_not_constant": "fun g() -> int {\n    return 1\n}\nconst F: () -> int = g\nfun main() {}\n",
    "test_on_struct": "#test(1)[1]\nstruct S { a: int }\nfun main() {}\n",
    "two_mains": "#main\nfun a() {}\n#main\nfun b() {}\n",
    "test_without_return": "#test()[1]\nfun f() {}\nfun main() {}\n",
    "test_two_expected": "#test()[1, 2]\nfun f() -> int {\n    return 1\n}\nfun main() {}\n",
    "destructure_declared_type": _main("let (a, b): (int, int) = (1, \"s\")"),
    "assign_mismatch": _main("var x = 1", "x = \"s\""),
    "range_of_strings": _main("for i in \"a\"..\"b\" {", "}"),
    "destructure_duplicate": _main("let (a, a) = (1, 2)"),
    "destructure_nested_non_tuple": _main("let ((a, b), c) = (1, 2)"),
    "assign_unknown": _main("y = 1"),
    "assign_field_of_int": _main("var x = 1", "x.f = 2"),
    "assign_missing_field": _main("var s = S { a: 1 }", "s.b = 2", before=_S),
    "assign_index_of_int": _main("var x = 1", "x[0] = 2"),
    "assign_list_index_str": _main("var xs = [1]", "xs[\"a\"] = 2"),
    # (`let x = print(1)` was one; since D140 a call without a result is `()`)
    "placeholder_value": _main("let x = _"),
    "lambda_param_type": _main("let f = (x) => x"),
    "lambda_duplicate_param": _main("let f = (x: int, x: int) => x"),
    "lambda_may_finish": _main("let f: (int) -> int = (x: int) => {", "    if x > 0 {", "        return 1", "    }", "}"),
    "lambda_inconsistent_returns": _main("let f = (x: int) => {", "    if x > 0 {", "        return 1", "    }",
                                         "    return \"s\"", "}"),
    "map_literal_key": _main("let m = [[1]: 2]"),
    "match_arm_without_value": _main("let x = match 1 {", "    1 => { print(1) },", "    _ => 2,", "}"),
    "match_all_arms_diverge": "fun f() -> int {\n    let x = match 1 {\n        _ => { return 1 },\n    }\n    return x\n}\nfun main() {}\n",
    "match_arm_types": _main("let x = match 1 {", "    1 => 1,", "    _ => \"s\",", "}"),
    "pattern_binds_twice": _main("match (1, 2) {", "    (a, a) => {},", "}"),
    "literal_against_list": _main("match [1] {", "    1 => {},", "    _ => {},", "}"),
    "literal_type": _main("match 1 {", "    \"s\" => {},", "    _ => {},", "}"),
    "tuple_pattern_on_int": _main("match 1 {", "    (a, b) => {},", "}"),
    "tuple_pattern_arity": _main("match (1, 2) {", "    (a, b, c) => {},", "}"),
    "enum_pattern_on_int": _main("match 1 {", "    Some(x) => {},", "    _ => {},", "}"),
    "pattern_other_enum": _main("match E.A {", "    F.C => {},", "    _ => {},", "}", before=_E),
    "pattern_unknown_variant": _main("match E.A {", "    E.D => {},", "    _ => {},", "}", before=_E),
    "pattern_payload_count": _main("match Some(1) {", "    Some(a, b) => {},", "    None => {},", "}"),
    "pattern_needs_payload": _main("match Some(1) {", "    Option.Some => {},", "    _ => {},", "}"),
    "struct_pattern_on_int": _main("match 1 {", "    S { a } => {},", "}", before=_S),
    "struct_pattern_other": _main("let t = T { b: 1 }", "match t {", "    S { a } => {},", "}", before=_S + "struct T { b: int }\n"),
    "struct_pattern_field_twice": _main("let s = S { a: 1 }", "match s {", "    S { a, a } => {},", "}", before=_S),
    "struct_pattern_unknown_field": _main("let s = S { a: 1 }", "match s {", "    S { b } => {},", "}", before=_S),
    "bool_not_exhaustive": _main("match true {", "    true => {},", "}"),
    "int_not_exhaustive": _main("match 1 {", "    1 => {},", "}"),
    "variant_arm_unreachable": _main("match Some(1) {", "    Some(x) => {},", "    None => {},", "    None => {},", "}"),
    "builtin_as_value": _main("let f = print"),
    "generic_function_as_value": _main("let f = id", before="fun id<T>(x: T) -> T {\n    return x\n}\n"),
    "negate_string": _main("let x = -\"s\""),
    "complement_float": _main("let x = ~1.5"),
    # (compare_strings, `"a" < "b"`, was one; since D165 strings are ordered
    # byte-wise: the checker's own cases, `errors_of`)
    "shift_float": _main("let x = 1.5 << 1"),
    "shift_by_float": _main("let x = 1 << 1.5"),
    "compose_two_args_left": _main("let f = (a: int, b: int) => a", "let g = (x: int) => x", "let h = f >> g"),
    "compose_two_args_right": _main("let f = (x: int) => x", "let g = (a: int, b: int) => a", "let h = f >> g"),
    "overload_operand_types": _main("let x = S { a: 1 } + 1", before=_S + "impl Add for S {\n    fun add(self, o: S) -> S {\n        return o\n    }\n}\n"),
    "bounded_operand_types": "fun f<T: Add>(a: T, b: int) -> T {\n    return a + b\n}\nfun main() {}\n",
    # (push_onto_call, push_arity, contains_arity, contains_on_list,
    # remove_immutable, build_arity, append_arity, append_to_int, len_arity,
    # len_of_int and chars_arity were the function forms' argument errors;
    # since MYLA-221 those builtins are methods only, and the methods' errors
    # are test_builtin_methods')
    "assert_arity": _main("assert()"),
    "panic_arity": _main("panic()"),
    "format_without_args": _main("let s = format()"),
    "method_arity": _main("let s = S { a: 1 }", "let n = s.f()", before=_SM),
    "method_argument": _main("let s = S { a: 1 }", "let n = s.f(\"x\")", before=_SM),
    "method_type_param": _main("let s = S { a: 1 }", "let n = s.h()", before=_SM),
    "generic_method_argument": _main("let s = S { a: 1 }", "let n = s.g(1, \"x\")", before=_SM),
    "exit_arity": _main("__exit()"),
    "function_value_arity": _main("let f = (x: int) => x", "let y = f(1, 2)"),
    "partial_of_int": _main("let x = 1", "let f = x(_)"),
    "partial_generic_method": _main("let s = S { a: 1 }", "let f = s.g(_, 1)", before=_SM),
    "partial_missing_method": _main("let x = 1", "let f = x.foo(_)"),
    "partial_unknown": _main("let f = nothing(_)"),
    "partial_of_index": _main("let fs = [(x: int) => x]", "let f = fs[0](_)"),
    "partial_generic_function": _main("let f = id(_)", before="fun id<T>(x: T) -> T {\n    return x\n}\n"),
    "partial_arity": _main("let f = g(_)", before="fun g(a: int, b: int) -> int {\n    return a\n}\n"),
    "partial_argument": _main("let f = g(_, \"s\")", before="fun g(a: int, b: int) -> int {\n    return a\n}\n"),
    "function_arity": _main("g()", before="fun g(a: int) {}\n"),
    "generic_call_inference": _main("let n = g()", before="fun g<T>() -> int {\n    return 1\n}\n"),
    "generic_call_argument": _main("g(1, \"s\")", before="fun g<T>(a: T, b: T) {}\n"),
    "variant_type_inference": _main("let e = G.K(1)", before=_P),
    "variant_argument": _main("let e = E.A(\"s\")", before=_P),
    "unknown_variant": _main("let e = E.C", before=_E),
    "variant_needs_arguments": _main("let e = E.A", before=_P),
    "field_of_int": _main("let x = 1", "let y = x.f"),
    "unknown_struct": _main("let s = Nope { a: 1 }"),
    "struct_literal_duplicate": _main("let s = S { a: 1, a: 2 }", before=_S),
    "struct_literal_field_type": _main("let s = S { a: \"x\" }", before=_S),
    "format_lone_close": _main("let s = format(\"a}\")"),
    "alias_not_generic": "typealias A = int\nfun f(x: A<int>) {}\nfun main() {}\n",
    "match_arm_int_types": _main("let x = match 1 {", "    1 => 1u8,", "    _ => 2i64,", "}"),
    "const_division_through_a_const": "const Z: int = 0\nconst Q: int = 1 / Z\nfun main() {}\n",
    "const_division_by_wrapped_zero": "const A: uint8 = 128\nconst Z: uint8 = A + A\nconst Q: int = 1 / (Z as int)\nfun main() {}\n",
    "const_division_by_negated_zero": "const A: int = 0\nconst Q: int = 1 % -A\nfun main() {}\n",
    "const_cycle": "const A: int = B\nconst B: int = A\nfun main() {}\n",
    "literal_above_uint64": _main("let x = 18446744073709551616u64"),
    "literal_above_int64": _main("let x = 9223372036854775809i64"),
    "literal_past_int64_max_without_minus": _main("let x: int32 = 9223372036854775808i64"),
    "literal_at_int64_min_under_minus": _main("let x: int32 = -9223372036854775808i64"),
    "literal_above_int32_default": _main("let x = 9223372036854775808"),
    "huge_hex_literal": _main("let x: uint8 = 0x1_0000_0000_0000_0000"),
    "shift_by_huge_literal": _main("let x = 1 << 9223372036854775808"),
    "or_pattern_rebinds": _main("match (1, 2) {", "    (x, x | x) => {},", "}"),
    # literal patterns outside the scrutinee's range (MYLA-7)
    "negative_pattern_on_unsigned": _main("let b: uint8 = 255", "match b {", "    -1 => {},", "    _ => {},", "}"),
    "pattern_above_signed_max": _main("let c: int8 = 0", "match c {", "    128 => {},", "    _ => {},", "}"),
    "pattern_below_signed_min": _main("let c: int8 = 0", "match c {", "    -129 => {},", "    _ => {},", "}"),
    "big_pattern_on_int64": _main("let c: int64 = 0", "match c {", "    9223372036854775808 => {},", "    _ => {},", "}"),
    "big_negative_pattern_on_uint64": _main("let c: uint64 = 0", "match c {", "    -9223372036854775808 => {},", "    _ => {},", "}"),
    # exhaustiveness and redundancy by pattern matrices (MYLA-14)
    "nested_match_missing_a_variant": _main("let x: Option<Result<int, str>> = None", "let n = match x {",
                                            "    Some(Ok(v)) => v,", "    None => 0,", "}"),
    "tuple_of_bools_not_covered": _main("let x = (true, false)", "let n = match x {",
                                        "    (true, _) => 1,", "    (false, true) => 2,", "}"),
    "redundant_nested_arm": _main("let x: Option<Result<int, str>> = None", "let n = match x {",
                                  "    Some(Ok(v)) => v,", "    Some(Ok(1)) => 1,", "    _ => 0,", "}"),
    "redundant_literal_arm": _main("let x = 3", "let n = match x {", "    1 => 1,", "    1 => 2,", "    _ => 0,", "}"),
    "redundant_after_true_false": _main("let x = true", "let n = match x {", "    true => 1,", "    false => 2,",
                                        "    _ => 0,", "}"),
    # (exhaustive, so the error is the last line)
    "exhaustive_nested_and_or_patterns": _main(
        "let x: Option<Result<int, str>> = None", "let a = match x {", "    Some(Ok(v)) => v,",
        "    Some(Err(e)) => 0,", "    None => 1,", "}", "let b = match (x, true) {", "    (None, _) => 0,",
        "    (Some(r), true) => 1,", "    (_, false) => 2,", "}", "let c = match true {", "    true | false => 1,", "}",
        "let z: bool = 1"),
    # (these fit; the error is the last line)
    "patterns_at_the_bounds_fit": _main("let c: int64 = 0", "match c {", "    -9223372036854775808 => {},",
                                        "    9223372036854775807 => {},", "    -0 => {},", "    _ => {},", "}",
                                        "let u: uint64 = 0", "match u {", "    18446744073709551615 => {},",
                                        "    -0 => {},", "    _ => {},", "}", "let z: bool = 1"),
    # several errors: every function's attributes and body are checked on
    # their own, after the declarations (MYLA-65, D80)
    "several_functions": ("fun f() -> int {\n    return \"a\"\n}\nfun g() {\n    let x: int = true\n    let y: int = \"x\"\n}\n"
                          "struct S { a: int }\nimpl S {\n    fun m(self) -> int {\n        return nope\n    }\n}\n"
                          "fun main() {\n    print(1 + \"x\")\n}\n"),
    "attributes_then_bodies": ("fun main() {\n    let x: int = true\n}\n#test(1, 2)[3]\nfun h(a: int) -> int {\n    return a\n}\n"
                               "#test(1)\nfun k(a: int) -> int {\n    return a\n}\n#nope\nstruct T { a: int }\n"),
    "entry_point_and_a_body": "fun main(x: int) {\n    let y: int = true\n}\n",
    "two_mains_and_a_body": "#main\nfun a() {}\n#main\nfun b() {}\nfun c() {\n    let y: int = true\n}\n",
    "a_declaration_error_stays_single": "fun f() {}\nfun f() {}\nfun main() {\n    let x: int = true\n}\n",
    "state_after_a_failed_loop": ("fun a() {\n    while true {\n        let x: int = \"s\"\n    }\n}\n"
                                  "fun b() {\n    break\n}\nfun main() {}\n"),
    "state_after_a_failed_lambda": ("fun a() {\n    let f = (x: int) => {\n        for i in 0..3 {\n            return \"s\" + 1\n        }\n        return 1\n    }\n}\n"
                                    "fun b() -> int {\n    let g = (y: int) => y + 1\n    continue\n}\nfun main() {}\n"),
    "state_after_a_failed_test_attribute": ("#test((x: int) => { return x + \"s\" })[1]\nfun a(f: (int) -> int) -> int {\n    return f(1)\n}\n"
                                            "#test(2)\nfun b(x: int) -> int {\n    return x\n}\nfun main() {}\n"),
    "generic_and_method_bodies": ("fun id<T>(x: T) -> T {\n    return x + 1\n}\nstruct P { a: int }\nimpl P {\n    fun f(self) -> str {\n        return self.a\n    }\n"
                                  "    fun g<U>(self, u: U) -> U {\n        return self\n    }\n}\nfun main() {\n    let p = P { a: 1, b: 2 }\n}\n"),
    # notes (MYLA-65): where an assigned variable is declared (through
    # indexing, tuple fields and match bindings; none for a receiver), the
    # first declaration, the return type (not from a lambda), "did you mean"
    "note_index_root": _main("let xs = [1, 2]", "xs[0] = 3"),
    "note_field_of_element": "struct P { x: int }\n" + _main("let ps = [P { x: 1 }]", "ps[0].x = 3"),
    "note_match_binding": _main("match Some(1) {", "    Some(n) => { n = 2 },", "    None => {},", "}"),
    "note_for_variable": _main("for i in 0..3 {", "    i = 1", "}"),
    "note_lambda_param": _main("let f = (a: int) => {", "    a = 1", "}"),
    "note_receiver": "struct C { n: int }\nimpl C {\n    fun f(self) {\n        self.n = 1\n    }\n}\nfun main() {}\n",
    "note_destructured": _main("let (a, b) = (1, 2)", "let (c, a) = (3, 4)"),
    "note_return_in_lambda": "fun f() -> int {\n    let g: (int) -> str = (x: int) => {\n        return x\n    }\n    return 1\n}\nfun main() {}\n",
    "note_return_generic": "fun id<T>(x: T) -> T {\n    return 1\n}\nfun main() {}\n",
    "suggest_const": "const LIMIT: int = 3\n" + _main("print(LIMTI)"),
    "suggest_function_value": "fun double(x: int) -> int {\n    return x * 2\n}\n" + _main("let f = doubel"),
    "suggest_variant": _main("let x: Option<int> = Nnoe"),
    "suggest_alias": "typealias Grid = [[int]]\nfun f(g: Gird) {}\nfun main() {}\n",
    "suggest_type_param": "fun f<Item>(x: Itme) {}\nfun main() {}\n",
    "suggest_primitive": "fun f(x: flaot64) {}\nfun main() {}\n",
    "suggest_struct_pattern_field": ("struct P { name: str }\n"
                                     + _main('let p = P { name: "a" }', "match p {", "    P { nmae } => {},", "}")),
    "suggest_struct_literal_field": "struct P { name: str }\n" + _main('let p = P { nmae: "a" }'),
    "suggest_lvalue": _main("var total = 0", "totl = 1"),
    "suggest_partial_method": ("struct S { a: int }\nimpl S {\n    fun scale(self, k: int) -> int {\n        return self.a * k\n    }\n}\n"
                               + _main("let s = S { a: 1 }", "let g = s.sacle(_)")),
    "suggest_in_scope_variable_call": _main("let handler = (x: int) => x", "handlr(1)"),
    "suggest_nothing_close": _main("let count = 1", "print(zzzzz)"),
    "suggest_alphabetically_first": _main("let rows_b = 1", "let rows_a = 2", "print(rows_c)"),
    "too_many": "".join(f"fun f{i}() {{\n    let x: int = true\n}}\n" for i in range(25)) + "fun main() {}\n",
    # concurrency (D89, MYLA-135)
    "async_method_without_await": (_SM.replace("    fun f(self", "    async fun f(self")
                                   + "async fun k(s: S) -> int {\n    return s.f(1)\n}\nfun main() {}\n"),
    "async_value_without_await": ("async fun k(f: async (int) -> int) -> int {\n    return f(1)\n}\n"
                                  "fun main() {}\n"),
    "async_let_mismatch": ("async fun g() -> int {\n    return 1\n}\n"
                           "async fun k() {\n    async let a: bool = g()\n}\nfun main() {}\n"),
    "async_let_duplicate": ("async fun g() -> int {\n    return 1\n}\n"
                            "async fun k() {\n    let a = 1\n    async let a = g()\n}\nfun main() {}\n"),
    "async_let_void": ("async fun g() {}\nasync fun k() -> int {\n    async let a = g()\n    await a\n"
                       "    return await a\n}\nfun main() {}\n"),
    "actor_field_assigned_from_outside": ("actor A { n: int }\nfun k(a: A) {\n    var b = a\n    b.n = 1\n}\n"
                                          "fun main() {}\n"),
    "actor_field_of_other_actor": ("actor A { n: int }\nactor B { m: int }\nimpl B {\n"
                                   "    fun f(self, a: A) -> int {\n        return a.n\n    }\n}\nfun main() {}\n"),
    "actor_partial_method": ("actor A { n: int }\nimpl A {\n    fun f(self, x: int) -> int {\n        return x\n    }\n}\n"
                             + _main("let a = A { n: 1 }", "let g = a.f(_)")),
    "actor_field_partial": ("actor A { cb: (int) -> int }\nfun k(a: A) {\n    let g = a.cb(_)\n}\nfun main() {}\n"),
    "actor_field_called": ("actor A { cb: (int) -> int }\nfun k(a: A) -> int {\n    return a.cb(1)\n}\nfun main() {}\n"),
    "async_partial_value": "async fun k(f: async (int) -> int) {\n    let g = f(_)\n}\nfun main() {}\n",
    "async_type_mismatch": ("async fun g(n: int) -> int {\n    return n\n}\n"
                            + _main("let f: (int) -> int = g")),
    "async_generic_mismatch": ("async fun apply<T>(f: async (T) -> T, x: T) -> T {\n    return await f(x)\n}\n"
                               "fun dec(n: int) -> int {\n    return n - 1\n}\n"
                               "async fun k() -> int {\n    return await apply(dec, 1)\n}\nfun main() {}\n"),
    "await_sync_call": "fun g() -> int {\n    return 1\n}\nasync fun k() -> int {\n    return await g()\n}\nfun main() {}\n",
    "await_in_sync_lambda": ("async fun g() -> int {\n    return 1\n}\n"
                             "async fun k() {\n    let f = () => await g()\n}\nfun main() {}\n"),
    "actor_self_call_async_method": ("actor A { n: int }\nimpl A {\n    async fun f(self) -> int {\n        return 1\n    }\n"
                                     "    fun g(self) -> int {\n        return self.f()\n    }\n}\nfun main() {}\n"),
}

# D95 (MYLA-146): the reentrancy warnings of actors' async methods, which
# both checkers give alike, the program still checking (and none where the
# idioms re-check after the `await` or reserve before it)
WARNINGS: dict[str, str] = {
    # a `__` primitive called from a program: a warning, once per place, also
    # in a lambda (D100, MYLA-186)
    'warn_primitive_called': 'fun main() {\n    let d = __getcwd()\n    let f = () => __io_errno()\n    print(f() + d.len())\n    __exit(0)\n}\n',
    'warn_reentrancy_stale_check': 'actor Pay {\n    n: int,\n}\nimpl Pay {\n    fun charge(var self) -> bool {\n        self.n = self.n + 1\n        return true\n    }\n}\nactor Inv {\n    stock: int,\n}\nimpl Inv {\n    async fun buy(var self, p: Pay) -> bool {\n        if self.stock == 0 {\n            return false\n        }\n        let paid = await p.charge()\n        self.stock = self.stock - 1\n        return true\n    }\n}\n',
    'warn_reentrancy_recheck_is_quiet': 'actor Pay {\n    n: int,\n}\nimpl Pay {\n    fun charge(var self) -> bool {\n        self.n = self.n + 1\n        return true\n    }\n}\nactor Inv {\n    stock: int,\n}\nimpl Inv {\n    async fun buy(var self, p: Pay) -> bool {\n        if self.stock == 0 {\n            return false\n        }\n        let paid = await p.charge()\n        if self.stock > 0 {\n            self.stock = self.stock - 1\n            return true\n        }\n        return false\n    }\n}\n',
    'warn_reentrancy_reserve_is_quiet': 'actor Pay {\n    n: int,\n}\nimpl Pay {\n    fun charge(var self) -> bool {\n        self.n = self.n + 1\n        return true\n    }\n}\nactor Inv {\n    stock: int,\n}\nimpl Inv {\n    async fun buy(var self, p: Pay) -> bool {\n        if self.stock == 0 {\n            return false\n        }\n        self.stock = self.stock - 1\n        let paid = await p.charge()\n        if !paid {\n            self.stock = self.stock + 1\n        }\n        return paid\n    }\n}\n',
    'warn_reentrancy_stale_value': 'actor Pay {\n    n: int,\n}\nimpl Pay {\n    fun charge(var self) -> bool {\n        self.n = self.n + 1\n        return true\n    }\n}\nactor Inv {\n    stock: int,\n}\nimpl Inv {\n    async fun restock(var self, p: Pay) {\n        let s = self.stock\n        let paid = await p.charge()\n        self.stock = s + 10\n    }\n}\n',
    'warn_reentrancy_push_and_loop': 'actor Pay {\n    n: int,\n}\nimpl Pay {\n    fun charge(var self) -> bool {\n        self.n = self.n + 1\n        return true\n    }\n}\nactor Inv {\n    stock: int,\n    sold: [str],\n    m: [str: int],\n}\nimpl Inv {\n    async fun record(var self, p: Pay, who: str) {\n        if self.sold.len() < 10 {\n            let paid = await p.charge()\n            self.sold.push(who)\n        }\n        let n = ["k": self.stock]\n        let again = await p.charge()\n        self.m = n\n    }\n    async fun drain(var self, p: Pay) {\n        while self.stock > 0 {\n            let paid = await p.charge()\n            self.stock = self.stock - 1\n        }\n    }\n}\n',
    'warn_reentrancy_match_and_lambda': 'actor Pay {\n    n: int,\n}\nimpl Pay {\n    fun charge(var self) -> bool {\n        self.n = self.n + 1\n        return true\n    }\n}\nactor Inv {\n    stock: Option<int>,\n    hits: int,\n}\nimpl Inv {\n    async fun take(var self, p: Pay) -> int {\n        let f = () => { return 1 }\n        match self.stock {\n            Some(n) => {\n                let paid = await p.charge()\n                self.stock = Some(n - f())\n            },\n            None => {},\n        }\n        let x = await p.charge()\n        self.hits = self.hits + 1\n        return self.hits\n    }\n}\n',
}


# MYLA-171: the D95 walk through `self` methods. A call of a `var self`
# method counts as a change of every field it changes, transitively; a call
# of a method as an examination of every field its body examines. (The
# Python checker never saw these, so the expectation is written here: the
# warnings' first lines, then `ok`.)
_PAY = "actor Pay {\n    n: int,\n}\nimpl Pay {\n    fun charge(var self) -> bool {\n        self.n = self.n + 1\n        return true\n    }\n}\n"
_INV_METHODS = ("    fun take(var self) {\n        self.stock = self.stock - 1\n    }\n"
                "    fun has_stock(self) -> bool {\n        return self.stock > 0\n    }\n"
                "    fun sell(var self) -> int {\n        self.take()\n        self.sold = self.sold + 1\n        return self.sold\n    }\n")
SELF_METHOD_WARNINGS: dict[str, tuple[str, list[str]]] = {
    # the change in a `var self` method
    "change_in_a_method": (_PAY + "actor Inv {\n    stock: int,\n    sold: int,\n}\nimpl Inv {\n" + _INV_METHODS +
        "    async fun buy(var self, p: Pay) -> bool {\n        if self.stock == 0 {\n            return false\n        }\n"
        "        let paid = await p.charge()\n        self.take()\n        return true\n    }\n}\n",
        ["warn 31 18 31:9-31:20 warning: 'self.stock' was checked before an 'await' and is changed after it: another call to this actor may have changed it meanwhile"]),
    # ... two calls deep
    "change_two_methods_deep": (_PAY + "actor Inv {\n    stock: int,\n    sold: int,\n}\nimpl Inv {\n" + _INV_METHODS +
        "    async fun buy(var self, p: Pay) -> int {\n        if self.stock == 0 {\n            return 0\n        }\n"
        "        let paid = await p.charge()\n        return self.sell()\n    }\n}\n",
        ["warn 31 25 31:16-31:27 warning: 'self.stock' was checked before an 'await' and is changed after it: another call to this actor may have changed it meanwhile"]),
    # the check in a method
    "check_in_a_method": (_PAY + "actor Inv {\n    stock: int,\n    sold: int,\n}\nimpl Inv {\n" + _INV_METHODS +
        "    async fun buy(var self, p: Pay) -> bool {\n        if !self.has_stock() {\n            return false\n        }\n"
        "        let paid = await p.charge()\n        self.stock = self.stock - 1\n        return true\n    }\n}\n",
        ["warn 31 13 31:9-31:19 warning: 'self.stock' was checked before an 'await' and is changed after it: another call to this actor may have changed it meanwhile"]),
    # the ways out: checking again after the `await`, changing before it
    "quiet_check_again": (_PAY + "actor Inv {\n    stock: int,\n    sold: int,\n}\nimpl Inv {\n" + _INV_METHODS +
        "    async fun buy(var self, p: Pay) -> bool {\n        if !self.has_stock() {\n            return false\n        }\n"
        "        let paid = await p.charge()\n        if self.has_stock() {\n            self.take()\n            return true\n        }\n        return false\n    }\n}\n",
        []),
    "quiet_change_before": (_PAY + "actor Inv {\n    stock: int,\n    sold: int,\n}\nimpl Inv {\n" + _INV_METHODS +
        "    async fun buy(var self, p: Pay) -> bool {\n        if !self.has_stock() {\n            return false\n        }\n"
        "        self.take()\n        let paid = await p.charge()\n        return paid\n    }\n}\n",
        []),
}

# MYLA-386: the D95 walk in a generic actor's async methods, through its
# generic synchronous methods: the same warnings as the same actor over
# `int` (the test checks both), written here since the Python checker had no
# generic actors. The warnings' first lines, then `ok`.
_SHELF = ("actor Shelf<T> {\n    items: [T],\n    sold: int,\n}\nimpl<T> Shelf<T> {\n"
          "    fun take(var self) -> T {\n        self.sold = self.sold + 1\n        return self.items.pop()\n    }\n"
          "    fun has(self) -> bool {\n        return self.items.len() > 0\n    }\n")
GENERIC_ACTOR_WARNINGS: dict[str, tuple[str, list[str]]] = {
    # a check through a method, a change by `pop` after the `await`
    "check_then_pop": (_PAY + _SHELF +
        "    async fun sell(var self, p: Pay) -> int {\n        if !self.has() {\n            return 0\n        }\n"
        "        let paid = await p.charge()\n        self.items.pop()\n        return 1\n    }\n}\n",
        ["warn 27 23 27:9-27:25 warning: 'self.items' was checked before an 'await' and is changed after it: another call to this actor may have changed it meanwhile"]),
    # a change through a method returning a `T`, inside an expression
    "change_in_a_method": (_PAY + _SHELF +
        "    async fun hand_over(var self, p: Pay) -> Option<T> {\n        if self.sold > 9 {\n            return None\n        }\n"
        "        let paid = await p.charge()\n        return Some(self.take())\n    }\n}\n",
        ["warn 27 30 27:21-27:32 warning: 'self.sold' was checked before an 'await' and is changed after it: another call to this actor may have changed it meanwhile"]),
    # a list of `T`s set from what was read before the `await`
    "stale_value": (_PAY + _SHELF +
        "    async fun restock(var self, p: Pay, x: T) {\n        let kept = self.items\n"
        "        let paid = await p.charge()\n        self.items = kept\n        self.items.push(x)\n    }\n}\n",
        ["warn 25 13 25:9-25:19 warning: 'self.items' is set from a value read before an 'await': another call to this actor may have changed it meanwhile"]),
    # checking again after the `await` is quiet
    "quiet_check_again": (_PAY + _SHELF +
        "    async fun sell(var self, p: Pay) -> Option<T> {\n        if !self.has() {\n            return None\n        }\n"
        "        let paid = await p.charge()\n        if self.has() {\n            return Some(self.take())\n        }\n        return None\n    }\n}\n",
        []),
}

# MYLA-394: a builtin mutator (`push`, `pop`, `remove`, `append`) or a `var
# self` method (std.list's `insert`, a struct's) on a field of `self` changes
# that field wherever it stands in an expression, not only as a statement.
# (This checker runs without the standard library, so the `var self` methods
# here are a struct's.) The warnings' first lines, then `ok`.
_COUNTER = ("struct Counter {\n    n: int,\n}\nimpl Counter {\n    fun bump(var self) -> int {\n        self.n += 1\n        return self.n\n    }\n"
            "    fun reset(var self) {\n        self.n = 0\n    }\n}\n")
_STALL = "actor Stall {\n    items: [int],\n    c: Counter,\n}\nimpl Stall {\n"
_SELL = "    async fun sell(var self, p: Pay) -> {ret} {{\n        if self.items.len() == 0 {{\n            return {none}\n        }}\n        let paid = await p.charge()\n{body}    }}\n}}\n"
FIELD_MUTATOR_WARNINGS: dict[str, tuple[str, list[str]]] = {
    "pop_in_a_let": (_PAY + _COUNTER + _STALL + _SELL.format(ret="int", none="0", body="        let x = self.items.pop()\n        return x\n"),
        ["warn 32 31 32:17-32:33 warning: 'self.items' was checked before an 'await' and is changed after it: another call to this actor may have changed it meanwhile"]),
    "pop_in_a_return": (_PAY + _COUNTER + _STALL + _SELL.format(ret="Option<int>", none="None", body="        return Some(self.items.pop())\n"),
        ["warn 32 35 32:21-32:37 warning: 'self.items' was checked before an 'await' and is changed after it: another call to this actor may have changed it meanwhile"]),
    "var_self_method_as_a_statement": (_PAY + _COUNTER + _STALL +
        "    async fun count(var self, p: Pay) -> int {\n        if self.c.n > 9 {\n            return 0\n        }\n"
        "        let paid = await p.charge()\n        self.c.reset()\n        return 1\n    }\n}\n",
        ["warn 32 21 32:9-32:23 warning: 'self.c' was checked before an 'await' and is changed after it: another call to this actor may have changed it meanwhile"]),
    "var_self_method_in_an_expression": (_PAY + _COUNTER + _STALL +
        "    async fun count(var self, p: Pay) -> int {\n        if self.c.n > 9 {\n            return 0\n        }\n"
        "        let paid = await p.charge()\n        return self.c.bump() + 1\n    }\n}\n",
        ["warn 32 27 32:16-32:29 warning: 'self.c' was checked before an 'await' and is changed after it: another call to this actor may have changed it meanwhile"]),
    "quiet_check_again": (_PAY + _COUNTER + _STALL + _SELL.format(ret="int", none="0",
        body="        if self.items.len() > 0 {\n            let x = self.items.pop()\n            return x\n        }\n        return 0\n"),
        []),
    "quiet_change_before": (_PAY + _COUNTER + _STALL +
        "    async fun sell(var self, p: Pay) -> int {\n        if self.items.len() == 0 {\n            return 0\n        }\n"
        "        let x = self.items.pop()\n        let paid = await p.charge()\n        return x\n    }\n}\n",
        []),
}

# Verdicts a later decision changed from the retired Python checker's
# recording, pinned here.
SUPERSEDED: dict[str, str] = {
    # D102: the unsuffixed 2.0 is a float64
    "unit_test_78": "err 3 8 3:8-3:9 type: type mismatch: 'int32' vs 'float64' (no implicit conversion between numeric types)",
    # D138: a #test case on a function without a result expects [()] (the review of 2026-11-06)
    "test_without_return": "err 1 9 1:9-1:10 type: '#test' on a function without a result expects '[()]'",
    # D140: an arm ending in a call of a function without a result is the value (), so the
    # arms disagree on their type instead of one lacking a value (the review of 2026-11-06)
    "match_arm_without_value": "err 4 14 4:14-4:15 type: match arms have incompatible types '()' and 'int32'",
    "unit_test_46": "err 8 14 8:14-8:15 type: match arms have incompatible types '()' and 'int32'",
    # D162: an async function takes cases; an async method still doesn't
    "unit_test_165": "err 5 5 5:5-5:25 type: '#test' can't run an async method (test it through an async test function, D162)",
    # D161: a method takes '#allow' too
    "unit_test_164": "err 5 5 5:5-5:10 type: attribute '#main' can't be applied to a method (a method takes only '#test' and '#allow')",
    # D163 (MYLA-313): map keys are the Eq + Hash types; tuples and lists are Eq (and Hash) when
    # their elements are; Hash is derivable
    "unit_test_76": "err 1 21 1:21-1:35 type: map key type must be Eq and Hash, found 'float64': 'float64' isn't Hash (NaN is unequal to itself)",
    "unit_test_144": "err 1 9 1:9-1:12 type: cannot derive 'Ord': only 'Eq', 'Hash' and 'Json' are derivable",
    "unit_test_156": "ok",
    "derive_on_generic": "err 1 1 1:1-1:12 type: deriving on generic types is not supported yet (Eq, Hash and Json are derived for concrete structs and enums)",
    "derive_enum_payload": "ok",
    "map_literal_key": "ok",
    # D165: `'a' - 'b'` is an int32 and `c + n` a char, but two chars don't add
    "unit_test_3": "err 1 24 1:20-1:29 type: operator '+' can't add two chars: 'c - d' is their distance (an 'int32'), 'c + n' moves 'c' by the 'int32' 'n'",
}

def _corpus() -> list[str]:
    """Every single-file .my source the checker gate covers: the top-level
    examples and the error corpus. (Multi-file example packages and the stdlib
    are import-driven; they are filtered out by `_oracle` below.)"""
    pats = [
        os.path.join(_REPO, "examples", "*.my"),
        os.path.join(_REPO, "examples", "errors", "*.my"),
    ]
    files: set[str] = set()
    for p in pats:
        files.update(glob.glob(p))
    return sorted(files)


def _snippets() -> dict[str, str]:
    with open(_SNIPPETS, encoding="utf-8") as fh:
        harvested = json.load(fh)
    cases = {f"unit_test_{i}": src for i, src in enumerate(harvested)}
    cases.update(TYPE_ERRORS)
    return cases


# The oracle's canonical lines: `err <line> <col> <span> <kind>: <message>`
# for an error and the errors after it (D80), the range a diagnostic
# underlines agreeing too (MYLA-65), else `ok` after the checker's warnings
# (D95), as check_main prints them.

@golden("selfhost_checker.verdict_of_source")
def _oracle_source(source: str) -> str:
    from myla.canon import canonical_errors, canonical_warning
    from myla.errors import MylaError
    from myla.lexer import tokenize
    from myla.parser import parse
    from myla.types import check
    try:
        checker = check(parse(tokenize(source)))
    except MylaError as err:
        return canonical_errors(err)
    return "\n".join([canonical_warning(w) for w in checker.warnings] + ["ok"])


@golden("selfhost_checker.verdict")
def _oracle(path: str) -> str | None:
    """Canonical accept/reject line from the Python toolchain, or None if the
    file is not part of the checker-parity gate (does not lex/parse cleanly, uses
    module imports, or rejects with a non-`type` diagnostic class)."""
    from myla.ast import ImportDecl
    from myla.canon import canonical_errors, canonical_warning
    from myla.errors import MylaError
    from myla.lexer import tokenize
    from myla.loader import default_stdlib_root, link
    from myla.parser import parse
    from myla.types import check
    with open(path, "r", encoding="utf-8") as fh:
        source = fh.read()
    try:
        program = parse(tokenize(source))
    except MylaError:
        return None  # lex/parse-error file: not part of the checker gate
    if any(isinstance(d, ImportDecl) for d in program.decls):
        return None  # import-driven: the self-hosted check_main has no loader
    try:
        checker = check(link(path, stdlib_root=default_stdlib_root()))
    except MylaError as err:
        kind = err.kind.split()[0]
        if kind != "type":
            return None  # only the `type` diagnostic class is in scope
        return canonical_errors(err)
    return "\n".join([canonical_warning(w) for w in checker.warnings] + ["ok"])


class SelfHostedCheckerParity(unittest.TestCase):
    _binary: str | None = None

    @classmethod
    def setUpClass(cls) -> None:
        # (The fallback of running check_main.my in the Python interpreter
        # went with the Python toolchain, MYLA-219; the self-hosted one needs
        # the native CLI, so a host without a native toolchain has neither.)
        if not CAN_BUILD_NATIVE:
            raise unittest.SkipTest(SKIP_REASON)
        # The Myla checker, built natively by the self-hosted compiler
        # (cached), so the gate also exercises the code generation of the
        # toolchain.
        cls._binary = selfhost_tool("check_main")

    def _myla_check(self, path: str) -> str:
        proc = subprocess.run(
            [self._binary, path], capture_output=True, text=True
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout.rstrip("\n")

    def test_corpus_check_parity(self) -> None:
        checked = 0
        unrecorded = 0
        for path in _corpus():
            try:
                expected = _oracle(path)
            except NoGolden:
                unrecorded += 1
                continue    # a file added to the corpus since has no recording: test_error_corpus holds it to the self-hosted CLI
            if expected is None:
                continue  # not part of the checker-parity gate
            with self.subTest(file=os.path.relpath(path, _REPO)):
                actual = self._myla_check(path)
                self.assertEqual(actual, expected)
                checked += 1
        # Guard against the corpus silently going empty; the unrecorded count
        # (new files held to the CLI's own output) says how far it has drifted
        self.assertGreater(checked, 60, f"{checked} compared, {unrecorded} without a recording")

    def test_type_errors_match_the_oracle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for name, source in _snippets().items():
                with self.subTest(case=name):
                    expected = SUPERSEDED.get(name) or _oracle_source(source)
                    # a later decision may have made the program valid ("ok", D163)
                    if name not in SUPERSEDED:
                        self.assertIn(" type: ", expected, "not a type error in Python")
                    path = os.path.join(tmp, name + ".my")
                    with open(path, "w", encoding="utf-8") as fh:
                        fh.write(source)
                    self.assertEqual(self._myla_check(path), expected)

    def test_warnings_match_the_oracle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for name, source in WARNINGS.items():
                with self.subTest(case=name):
                    expected = _oracle_source(source)
                    self.assertTrue(expected.endswith("ok"), expected)
                    self.assertEqual("warn " in expected, "quiet" not in name, expected)
                    path = os.path.join(tmp, name + ".my")
                    with open(path, "w", encoding="utf-8") as fh:
                        fh.write(source)
                    self.assertEqual(self._myla_check(path), expected)

    def test_warnings_through_self_methods(self) -> None:
        # MYLA-171: the two shapes of the review warn, the ways out stay quiet
        with tempfile.TemporaryDirectory() as tmp:
            for name, (source, warns) in SELF_METHOD_WARNINGS.items():
                with self.subTest(case=name):
                    path = os.path.join(tmp, name + ".my")
                    with open(path, "w", encoding="utf-8") as fh:
                        fh.write(source)
                    lines = self._myla_check(path).split("\n")
                    self.assertEqual([l for l in lines if l.startswith("warn ")], warns)
                    self.assertEqual(lines[-1], "ok")

    def test_warnings_in_generic_actors(self) -> None:
        # MYLA-386: D95 in a generic actor, as in the same actor over `int`
        with tempfile.TemporaryDirectory() as tmp:
            for name, (source, warns) in GENERIC_ACTOR_WARNINGS.items():
                concrete = (source.replace("actor Shelf<T>", "actor Shelf").replace("impl<T> Shelf<T>", "impl Shelf")
                            .replace("[T]", "[int]").replace("<T>", "<int>").replace("-> T ", "-> int ")
                            .replace("x: T", "x: int"))
                self.assertIsNone(re.search(r"\bT\b", concrete), concrete)
                for kind, text in [("generic", source), ("concrete", concrete)]:
                    with self.subTest(case=name, kind=kind):
                        path = os.path.join(tmp, f"{name}_{kind}.my")
                        with open(path, "w", encoding="utf-8") as fh:
                            fh.write(text)
                        lines = self._myla_check(path).split("\n")
                        self.assertEqual([l for l in lines if l.startswith("warn ")], warns)
                        self.assertEqual(lines[-1], "ok")

    def test_warnings_of_field_mutators(self) -> None:
        # MYLA-394: a field's mutator inside an expression, as a statement's
        with tempfile.TemporaryDirectory() as tmp:
            for name, (source, warns) in FIELD_MUTATOR_WARNINGS.items():
                with self.subTest(case=name):
                    path = os.path.join(tmp, name + ".my")
                    with open(path, "w", encoding="utf-8") as fh:
                        fh.write(source)
                    lines = self._myla_check(path).split("\n")
                    self.assertEqual([l for l in lines if l.startswith("warn ")], warns)
                    self.assertEqual(lines[-1], "ok")

    def test_declaration_mutants_match_the_oracle(self) -> None:
        # every example with one declaration broken (MYLA-110): the same error,
        # then the same silence where bodies depend on the broken part
        with tempfile.TemporaryDirectory() as tmp:
            for name, source, _first in mutants():
                with self.subTest(mutant=name):
                    path = os.path.join(tmp, name + ".my")
                    with open(path, "w", encoding="utf-8") as fh:
                        fh.write(source)
                    self.assertEqual(self._myla_check(path), _oracle_source(source))


if __name__ == "__main__":
    unittest.main()
