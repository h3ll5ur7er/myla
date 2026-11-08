---
id: MYLA-354
title: "Decision: serialisation by derive"
type: chore
status: backlog
priority: low
labels: [decision, language, stdlib, wave-4]
---
Wave 4 of [[Project/Standard-library-roadmap]], roadmap #58. Whether `#derive(Json)` (or a serialisation trait with a derive, as `Eq` and `Hash` have) converts structs and enums to and from `std.json`'s values, and later TOML and YAML. A language decision first: what the derive generates, field names and renames, `Option` fields, enums.

- **Needs:** [[MYLA-332]]

- [x] Options and a recommendation written here for the owner
- [ ] The decision recorded

## Options (for the owner, 2026-11-08)

What it is about. Today a struct goes to JSON and back by hand: one `to_json` and one `from_json` per type, each field spelt twice. A derive writes them:

```myla fragment
#derive(Json)
struct Point {
    x: int,
    y: int,
    label: Option<str>,
}

fun main() {
    let text = json.to_string(Point { x: 1, y: 2, label: None }.to_json())   // {"x":1,"y":2}
    let p: Point = json.decode(text)?                                        // back again
}
```

What the language has today, which bounds the choices:

- `#derive(Eq, Hash)` generates Myla source for the impl and checks it with the program (`derived_hash_src`, `synthesize_derives` in [[selfhost/checker.my]]). A JSON derive can work the same way.
- Encoding is easy: a method `to_json(self) -> Json`.
- **Decoding is not.** It must make a `T` with no `T` in hand, and Myla has no functions without `self`: "every method takes `self`". A generic `json.decode<T>(j)` can't call anything on `T`.
- Fields have no attributes (`Field` in [[selfhost/ast.my]] carries none), so per-field renames need a parser change.
- `#derive` refuses generic types (MYLA-379).

### The questions

1. **How decoding makes a value.**
   - **A. Trait functions without `self` (recommended).** A trait may declare `fun from_json(j: Json) -> Result<Self, JsonError>`, called on a type or a type parameter: `Point.from_json(j)`, `T.from_json(j)`. With it, `json.decode<T: FromJson>(text)` works, and so would a `Default` or `Zero` trait. `iter.sum(0)` could then lose its zero argument ([[MYLA-381]]), and `set.new()`-style constructors could live in traits. It is a language change: the parser, the checker, both backends and the language server, with its own seed.
   - **B. A generated free function per type,** `point_from_json(j)`. No language change, but there is no generic `decode<T>`, and the names are made up.
   - **C. Decode into a value you already have:** `var p = Point { x: 0, y: 0, label: None }; p.read_json(j)?`. No language change, but you must write a dummy value first, and a nested field's type needs one too.
2. **Which values the derive targets.**
   - **`Json` (recommended).** `std.json`'s enum is the standard library's general value. `std.yaml` (MYLA-349) and `std.toml` convert to and from it, so one derive serves all three formats.
   - **Or a new format-neutral `std.data.Value`** that every format converts. That is cleaner in theory, but it is one more module and every format gains a conversion, for no case JSON's values can't carry today.
3. **Names.** Fields are written as they are named.
   - **No renames in the first version (recommended),** since that needs attributes on fields (`#name("first-name")`), a parser change of its own.
   - **Or a type-level `#derive(Json)` option** (`rename_all = "kebab"`), which also needs attribute arguments.
4. **`Option` fields.**
   - **Recommended:** `None` is written as an absent field and read back from an absent field or `null`. A missing non-`Option` field is an error naming its path (`$.items[2].label`). Unknown fields are ignored.
   - **Or strict:** an unknown field is an error.
5. **Enums.**
   - **Recommended, serde's default ("externally tagged"):** a variant without a payload is its name as a string (`"Red"`); one with a payload is an object with one key (`{"Circle": [1, 2]}`, or `{"Circle": 1}` for a single payload).
   - **Or "internally tagged"** (`{"type": "Circle", …}`). That doesn't fit Myla, whose variant payloads are positional, not named.
6. **Numbers.**
   - **Integers:** a sized integer is checked on reading: out of range is an error, never wrapped. A `uint64` above `int64`'s range can't be a `Json.Int`; the recommendation is to write it as a float with an error on reading if it isn't exact, or the alternative, an error on writing.
   - **Floats:** NaN and the infinities aren't JSON. Recommended: writing stays infallible and writes `null`, as JavaScript does; the alternative is a fallible `to_json`.
7. **Errors (D168):** a struct with a `kind` (missing field, wrong type, out of range, unknown variant) and the path where it happened.

### Recommendation

- **The language part (1 A):** trait functions without `self`. A compiler task with its own pull request and seed.
- **The derive (2–7):** `#derive(Json)` generating `impl ToJson` and `impl FromJson` against `Json`; names as written; `Option` as an absent field; externally tagged enums; checked integers; non-finite floats as `null`; errors with a path.
- **Order:** first the language part, then the derive in the checker, then `json.decode<T>` and `json.encode`. `#derive` on generic types (MYLA-379) can follow.

Alternatives:

- **B or C instead of A:** no language change, but no generic `decode<T>`; you write either a made-up function name or a dummy value.
- **No derive:** keep writing the conversions by hand, as today.
