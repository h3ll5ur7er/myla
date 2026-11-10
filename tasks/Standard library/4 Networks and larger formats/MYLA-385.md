---
id: MYLA-385
title: "#derive(Json), json.encode and json.decode<T>"
type: feature
status: done
priority: medium
labels: [stdlib, json, derive]
---
The derive of D172 ([[MYLA-354]]), after [[MYLA-384]].

- [x] `trait ToJson { fun to_json(self) -> Json }` and `trait FromJson { fun from_json(j: Json) -> Result<Self, JsonError> }` in `std.json`, implemented for the built-in types (integers checked for range on reading, floats, `bool`, `str`, `char`?, lists, `Option`, maps with `str` keys)
- [x] `#derive(Json)` on structs and enums, generated as source as `#derive(Hash)` is: fields as written; `Option` fields absent when `None`, read from absent or `null`; unknown fields ignored; enums externally tagged
- [x] `json.encode<T: ToJson>(v) -> str`, `json.decode<T: FromJson>(text) -> Result<T, JsonError>`, with the error's path (`$.items[2].label`)
- [x] YAML and TOML through their `Json` conversions, one example each
- [x] Parity programs and the error corpus (a field type that isn't `Json`, a derive on a generic type while MYLA-379 stands)

## What was built

**std.json** ([[lib/std/json.my]], [[Language/Standard-library/Json#typed-values]]):

- `pub trait ToJson`, `pub trait FromJson` (a function without `self`, D172), `encode<T: ToJson>(v) -> str`, `decode<T: FromJson>(text) -> Result<T, JsonError>`.
- Impls for `int8` … `int64`, `uint8` … `uint64`, `float32`, `float64`, `bool`, `str`, `char` (a one-character string), `Json` (itself), `impl<T: ToJson> ToJson for [T]`, `impl<V: ToJson> ToJson for [str: V]`, `impl<T: ToJson> ToJson for Option<T>` and their `FromJson`s. Integers are range-checked on reading; a whole `Float` (`2.0`, `1e3`) reads as an integer, a fraction is `WrongType`; a `uint64` beyond `int64` is written as the nearest float and read back only below 2^64; a non-finite float is `null`; a `float32` is written in its shortest form (`0.1`).
- **Errors: `JsonError` keeps D168's shape, a struct with a `kind`**, and gains two fields: `kind: JsonErrorKind` (`Syntax`, `MissingField`, `WrongType`, `OutOfRange`, `UnknownVariant`) and `path: str`. `parse`'s errors are `Syntax` with their line and column and an empty path; decoding errors have the path (`$`, `.name`, `[2]`, `["a b"]` for a key that isn't a name) and line and column 0 (a `Json` value keeps no positions). It is `Eq`, has `message()` and `impl Format` (`line:col: msg`, `path: msg`), as D168 asks; `msg`, `line`, `col` stay, so existing readers of `e.msg` are unchanged.
- Helpers for an impl written by hand, which the derive also calls: `wrong_type(expected, found)`, `members(j, name)`, `member<T>(fields, name)`, `optional_member<T>(fields, name)`; and the derive's enum helpers `variant_of`, `unit_variant`, `payload`, `unknown_variant` (private).

**The derive** ([[selfhost/checker.my]] `derive_json`, `derived_json_struct_src`, `derived_json_enum_src`, `is_json_type`, `json_prefix`): written as Myla source and checked with the program, as `#derive(Hash)` is. Unlike `Hash`, whose names are the prelude's, the source names std.json's items, which the loader has qualified (`std$json$Json`); [[selfhost/lexer.my]] gains `lex_qualified` (a `$` continues an identifier) and [[selfhost/parser.my]] `parse_qualified`, used only for this source. For `struct P { x: int, tag: Option<str> }`:

```myla fragment
impl std$json$ToJson for P {
    fun to_json(self) -> std$json$Json {
        var out: [(str, std$json$Json)] = []
        out.push(("x", self.x.to_json()))
        if let Some(v) = self.tag {
            out.push(("tag", v.to_json()))
        }
        return std$json$Json.Object(out)
    }
}

impl std$json$FromJson for P {
    fun from_json(j: std$json$Json) -> Result<P, std$json$JsonError> {
        let fields = std$json$members(j, "P")?
        return Ok(P {
            x: std$json$member<int32>(fields, "x")?,
            tag: std$json$optional_member<str>(fields, "tag")?,
        })
    }
}
```

and for `enum E { A, B(str), C(int, [bool]) }` `match self { A => Json.Str("A"), B(field0) => Json.Object([("B", field0.to_json())]), C(field0, field1) => Json.Object([("C", Json.Array([…]))]) }` and `match v.0 { "A" => unit_variant(v, "E", E.A), "B" => Ok(E.B(payload<str>(v, "E", 1, 0)?)), …, _ => Err(unknown_variant(v.0, "E", ["A", "B", "C"])) }` after `let v = variant_of(j, "E")?`. A field's type is written as an explicit type argument (D169), so lists, maps and `Option`s of any depth need no syntax of their own.

The checks: a field or payload must be a scalar, `str`, `char`, `Json`, a list, a map with `str` keys, an `Option`, or a type that derives `Json` or writes both impls, else `cannot derive Json for struct 'Edge': field 'ends' has type '(int32, int32)', which isn't ToJson and FromJson (a tuple has no JSON form: make it a struct)` (a map with other keys: `(a map is an object only with 'str' keys)`); a type that derives `Json` and writes either impl, `type 'Point' both derives Json and has an explicit 'impl ToJson for Point'`; without std.json, `cannot derive Json for 'Point': std.json isn't imported (write 'import std.json as json')`; a generic type, MYLA-379's message, now `deriving on generic types is not supported yet (Eq, Hash and Json are derived for concrete structs and enums)`. A bound std.json's traits don't meet, `json.decode<Point>(…)` of a type without them, says `type 'Point' does not satisfy the bound 'T: FromJson' required by 'decode'` with the help `'#derive(Json)' on 'Point' gives it 'ToJson' and 'FromJson' (D172)`; that message now names a module's trait and function without the loader's prefix (it said `T: std$json$FromJson` … `std$json$decode`).

**D164.** D164 (1) puts operations on the built-in types, as *inherent methods*, in the implicit modules; D166 made std.hash implicit because `Hash` is the prelude's and its impls must be seen wherever a map key is, import or not. `ToJson` and `FromJson` are std.json's own traits: no program can name them, call `encode`/`decode` or derive `Json` without importing std.json, so their impls for the built-in types are needed exactly where std.json is loaded, and belong with the trait (Rust's coherence rule: an impl lives with its trait or its type). They are trait impls, not new inherent methods, so they stay in std.json and no decision is needed; making std.json implicit instead would cost every program its check. Said on [[Language/Standard-library/Json]].

## Evidence

Built on `81fe44e`. Tests first: the four parity programs failed before the change (`cannot derive 'Json': only 'Eq' and 'Hash' are derivable`, `module does not export 'encode'`, `module 'std.json' does not export 'JsonErrorKind'`).

- **Parity** (`tests/burn/test_compiler_parity.py`, all `PINNED`): `json_derive_structs` (nested structs, lists, maps, `Option` fields absent, `null` and present, every built-in type, `float32` 0.1, `uint64` max and 2^63, NaN as `null`, an empty struct, round trips), `json_derive_enums` (every variant shape, inside structs and lists, `Option<Color>`), `json_derive_recursive` (`struct Tree { kids: [Tree] }`, a recursive enum, mutually recursive structs), `json_derive_errors` (a missing field `$.items[2].label`, a wrong type, `int8` 128 and -129, a fraction, an unknown variant with the expected names, a payload of the wrong size, a unit variant with a payload and the reverse, a quoted map key `$.extra["a b"]`, a syntax error, `char`, `uint64` and `int32` range), and `test_json_derive_across_modules` (a derive in a module whose names the loader qualifies, `geo$Point`, its types fields of a derived struct in another, `geo.Point` as the decoded type). 5/5 on x86-64 (interpreter = native), and with `MYLA_TEST_TARGET=aarch64-linux` (qemu) 5/5 and `MYLA_TEST_TARGET=wasm32-wasi` (Node) 5/5; the scratch copies built with `--target` and run under `qemu-aarch64` and `node tools/wasm/run.mjs` print what the interpreter prints.
- **std.json's cases**: 55 → 89 (`#test` cases of `wrong_type`, `members`, `key_step`, `described`, `variant_of`, `unknown_variant`, `int_in`, the impls of `uint64`, `float64`, `float32`, `char`, `JsonError`'s `message` and `format`; test functions `built_in_types_round_trip`, `encodes_and_decodes`, `reads_variants`): 89/89 interpreted, `--native` and `--target aarch64-linux`.
- **Error corpus**, pinned with `.stderr`: [[examples/errors/type_derive_json_field_not_json.my]] (a tuple field), [[examples/errors/type_derive_json_field_type_not_derived.my]] (`Option<User>`), [[examples/errors/type_derive_json_map_key.my]] (an `[int: str]` payload), [[examples/errors/type_derive_json_generic.my]], [[examples/errors/type_derive_json_without_std_json.my]], [[examples/errors/type_derive_json_and_impl.my]], [[examples/errors/type_decode_not_from_json.my]] (with its help); [[examples/errors/type_derive_unknown_trait.my]]'s pin names `Json`.
- **The checker's cases**: `derived_json_struct_src` (2), `derived_json_enum_src`, `is_json_type` (5), `json_note` (2), `unqualified` (2), `option_of` (2), `json_prefix`, `json_help`, and four `errors_of` programs (no std.json, a tuple field and an `[str: Q]` payload against a std.json stand-in, a generic type); the lexer's `lex_qualified`, the parser's `parses_qualified` (2). `myla test`: `selfhost/checker.my` 722/722, `selfhost/lexer.my` 57/57, `selfhost/parser.my` 172/172. `test_selfhost_checker`'s two pinned derive messages follow.
- **Docs**: [[Language/Standard-library/Json]] "Typed values" (a tested block for the derive, one for an impl by hand, one for YAML, one for TOML), its `JsonError` row; [[Language/Methods-and-traits]] (the derive list), [[Language/Attributes-and-testing]], [[Language/Standard-library]]; the `myla` skill, both copies. D172's row stands: nothing was decided differently; the page records the details it left open (a whole float reads as an integer, `null` isn't a float, a variant without payload is read from its string only, the path syntax).
- **Check time** of a hello world importing std.json (`myla check`, the same compiler with the library before and after, three interleaved rounds of 15, medians): 70–73 ms before, 75–78 ms after, +5 ms (+7 %); with the embedded library, 65 → 71 ms on a quieter machine. The ~40 small impls and the helpers are the cost; a program without std.json pays nothing.
- **YAML and TOML**: std.yaml's `to_json`/`from_json` carry a derived type both ways (the page's block). std.toml has no `Json` conversion, and the compiler imports std.toml (`selfhost/project.my`), so adding one there would make the compiler import std.json; the page's block writes the eight-line conversion instead.
- The bootstrap reaches its byte-identical fixed point (18,328,497 bytes). The compiler's own sources and the library modules it imports use none of the new derive; `selfhost/embedded_std.my` is left at the seed's (D156: the pull request's last commit runs `scripts/update-seed.sh`).
- `scripts/test.sh fast`: 718 tests, OK (3 skipped). `python3 -m unittest tests.burn.test_compiler_parity tests.burn.test_selfhost_cases tests.burn.test_error_corpus tests.burn.test_selfhost_checker tests.burn.test_std_modules tests.burn.test_doc_blocks tests.burn.test_lsp`: 687 tests, OK (the error corpus alone 300). Both with the regenerated `selfhost/embedded_std.my`; with the seed's, restored for the commit, `test_embedded_std` fails until the pull request's seed commit.

## Found on the way

- **A bound can't name a module's trait**: `fun show<T: json.ToJson>(v: T)` is `parse error: expected '>' to close type parameters, found '.'`; D170 covers types (`json.JsonError`), not bounds. Workaround: `from std.json import ToJson`, then `T: ToJson`.
- The LSP's resolution corpus test takes every identifier named like a declaration to be resolved, so a file that declares a method `format` (an `impl Format`) can't call the builtin `format(…)`: std.json now writes f-strings there.

## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]], with a follow-up in [[MYLA-424]]: a `uint64` above 2^63 silently loses its low bits; -2^63-1 reads as `int64`'s minimum.
