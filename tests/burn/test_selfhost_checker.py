"""Differential burn test for the self-hosted type checker (self-hosting v0.7).

`selfhost/checker.my` is the Myla-written type checker; `selfhost/check_main.my`
lexes + parses + type-checks a single-file program and prints the stable
accept/reject line (`ok`, else `err <line> <col> <span> type: <message>` for
each error, MYLA-65, D80). This test asserts that, for every single-file source
in the shared corpus and for every snippet of TYPE_ERRORS, those lines are
identical to the Python oracle's: the same verdict, errors in the same order,
positions, underlined ranges (MYLA-65) and messages (MYLA-28). That is the v0.7
checker-parity gate from docs/Development/Testing.md.

As with the lexer/parser gates, the Myla checker runs as a *native binary* when
the host can build one (which also exercises interpreter/compiler parity of the
toolchain that built it); otherwise it falls back to the interpreter.

The gate covers single-file programs that lex + parse cleanly and do not import
other modules (the self-hosted `check_main` has no module loader; it injects only
the `Option`/`Result`/`get` prelude, matching a no-import `myla check`). Files
that fail to lex/parse, or that use `import`, are excluded — they belong to the
lexer/parser gates or the runtime corpus, not the checker-parity gate.
"""
from __future__ import annotations

import glob
import io
import json
import os
import subprocess
import tempfile
import unittest

from myla.ast import ImportDecl
from myla.canon import canonical_errors
from myla.errors import MylaError
from myla.interpreter import Interpreter
from myla.lexer import tokenize
from myla.loader import default_stdlib_root, link
from myla.parser import parse
from myla.types import check

from ._mutants import mutants
from ._native import CAN_BUILD_NATIVE
from ._tools import selfhost_tool

_REPO = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
)
CHECK_TOOL = os.path.join(_REPO, "selfhost", "check_main.my")

# Programs the Python unit tests expect to fail type checking, collected by
# scripts/harvest_type_errors.py, then snippets for the messages they don't
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
    "generic_impl_on_builtin": "impl<T> int {\n    fun f(self) -> int {\n        return 1\n    }\n}\nfun main() {}\n",
    "impl_on_list": "impl [int] {\n    fun f(self) -> int {\n        return 1\n    }\n}\nfun main() {}\n",
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
    "push_onto_call": _main("push(g(), 1)", before="fun g() -> [int] {\n    return [1]\n}\n"),
    "no_value": _main("let x = print(1)"),
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
    "compare_strings": _main("let b = \"a\" < \"b\""),
    "shift_float": _main("let x = 1.5 << 1"),
    "shift_by_float": _main("let x = 1 << 1.5"),
    "compose_two_args_left": _main("let f = (a: int, b: int) => a", "let g = (x: int) => x", "let h = f >> g"),
    "compose_two_args_right": _main("let f = (x: int) => x", "let g = (a: int, b: int) => a", "let h = f >> g"),
    "overload_operand_types": _main("let x = S { a: 1 } + 1", before=_S + "impl Add for S {\n    fun add(self, o: S) -> S {\n        return o\n    }\n}\n"),
    "bounded_operand_types": "fun f<T: Add>(a: T, b: int) -> T {\n    return a + b\n}\nfun main() {}\n",
    "assert_arity": _main("assert()"),
    "panic_arity": _main("panic()"),
    "push_arity": _main("var xs = [1]", "push(xs)"),
    "contains_arity": _main("let b = contains([1: 2])"),
    "contains_on_list": _main("let b = contains([1], 1)"),
    "remove_immutable": _main("let m = [1: 2]", "remove(m, 1)"),
    "format_without_args": _main("let s = format()"),
    "build_arity": _main("let s = build()"),
    "append_arity": _main("var sb = StringBuilder()", "append(sb)"),
    "append_to_int": _main("var x = 1", "append(x, \"s\")"),
    "method_arity": _main("let s = S { a: 1 }", "let n = s.f()", before=_SM),
    "method_argument": _main("let s = S { a: 1 }", "let n = s.f(\"x\")", before=_SM),
    "method_type_param": _main("let s = S { a: 1 }", "let n = s.h()", before=_SM),
    "generic_method_argument": _main("let s = S { a: 1 }", "let n = s.g(1, \"x\")", before=_SM),
    "exit_arity": _main("__exit()"),
    "len_arity": _main("let n = len()"),
    "len_of_int": _main("let n = len(1)"),
    "chars_arity": _main("let c = chars()"),
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
    "literal_at_int64_magnitude_is_fine_but_wrong_type": _main("let x: int32 = 9223372036854775808i64"),
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


def _canonical(err: MylaError) -> str:
    """`err <line> <col> <span> <kind>: <message>` for `err` and the errors
    after it (D80): the range a diagnostic underlines must agree too
    (MYLA-65)."""
    return canonical_errors(err)


def _snippets() -> dict[str, str]:
    with open(_SNIPPETS, encoding="utf-8") as fh:
        harvested = json.load(fh)
    cases = {f"unit_test_{i}": src for i, src in enumerate(harvested)}
    cases.update(TYPE_ERRORS)
    return cases


def _oracle_source(source: str) -> str:
    try:
        check(parse(tokenize(source)))
    except MylaError as err:
        return _canonical(err)
    return "ok"


def _oracle(path: str) -> str | None:
    """Canonical accept/reject line from the Python toolchain, or None if the
    file is not part of the checker-parity gate (does not lex/parse cleanly, uses
    module imports, or rejects with a non-`type` diagnostic class)."""
    with open(path, "r", encoding="utf-8") as fh:
        source = fh.read()
    try:
        program = parse(tokenize(source))
    except MylaError:
        return None  # lex/parse-error file: not part of the checker gate
    if any(isinstance(d, ImportDecl) for d in program.decls):
        return None  # import-driven: the self-hosted check_main has no loader
    try:
        check(link(path, stdlib_root=default_stdlib_root()))
    except MylaError as err:
        kind = err.kind.split()[0]
        if kind != "type":
            return None  # only the `type` diagnostic class is in scope
        return _canonical(err)
    return "ok"


def _check_file(path: str):
    return link(path, stdlib_root=default_stdlib_root())


class SelfHostedCheckerParity(unittest.TestCase):
    _binary: str | None = None

    @classmethod
    def setUpClass(cls) -> None:
        if not CAN_BUILD_NATIVE:
            return
        # The Myla checker, built natively by the Python backend (cached), so
        # the gate also exercises the codegen parity of the toolchain.
        cls._binary = selfhost_tool("check_main")

    def _myla_check(self, path: str) -> str:
        if self._binary is not None:
            proc = subprocess.run(
                [self._binary, path], capture_output=True, text=True
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            return proc.stdout.rstrip("\n")
        # Interpreter fallback (no native toolchain on this host).
        out = io.StringIO()
        Interpreter(
            check(_check_file(CHECK_TOOL)), out, argv=["check_tool", path]
        ).run()
        return out.getvalue().rstrip("\n")

    def test_corpus_check_parity(self) -> None:
        checked = 0
        for path in _corpus():
            expected = _oracle(path)
            if expected is None:
                continue  # not part of the checker-parity gate
            with self.subTest(file=os.path.relpath(path, _REPO)):
                actual = self._myla_check(path)
                self.assertEqual(actual, expected)
                checked += 1
        # Guard against the corpus silently going empty.
        self.assertGreater(checked, 60)

    def test_type_errors_match_the_oracle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for name, source in _snippets().items():
                with self.subTest(case=name):
                    expected = _oracle_source(source)
                    self.assertIn(" type: ", expected, "not a type error in Python")
                    path = os.path.join(tmp, name + ".my")
                    with open(path, "w", encoding="utf-8") as fh:
                        fh.write(source)
                    self.assertEqual(self._myla_check(path), expected)

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
