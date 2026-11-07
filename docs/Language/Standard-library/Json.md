# std.json

JSON values, parsing and writing ([[MYLA-79]]), following Python's `json` module: the burn tests compare them on thousands of random and broken texts.

```myla
from std.json import Json, parse, to_string, field

fun main() {
    match parse("{\"id\": 1, \"method\": \"initialize\"}") {
        Ok(msg) => {
            match field(msg, "method") {
                Some(Json.Str(m)) => { print(m) },
                _ => { print("no method") },
            }
            print(to_string(Json.Array([Json.Int(1), Json.Null])))
        },
        Err(e) => { print(format("{}:{}: {}", e.line, e.col, e.msg)) },
    }
}
// output:
// initialize
// [1,null]
```

| Item | Meaning |
| --- | --- |
| `enum Json { Null, Bool(bool), Int(int64), Float(float64), Str(str), Array([Json]), Object([(str, Json)]) }` | A number without fraction or exponent that fits in int64 is an `Int`, any other a `Float`; an object keeps its members in order, duplicates included |
| `parse(text: str) -> Result<Json, JsonError>` | One value, with whitespace around it allowed |
| `struct JsonError { msg: str, line: int32, col: int32 }` | Python 3.13's messages and positions (the column counts characters) |
| `to_string(j: Json) -> str` | Compact text, as `json.dumps(j, ensure_ascii=False, separators=(",", ":"))` writes it: floats in their shortest form, control characters escaped, other characters as they are |
| `field(j: Json, key: str) -> Option<Json>` | An object's member (the last one with that key, as Python keeps it) |
| `at(j: Json, path: str) -> Option<Json>` | The value at a path, below |
| `pretty(j: Json, indent: int = 2) -> str` | Text with one item or member on a line, below |
| `obj(members: [(str, Json)])`, `arr(items: [Json])`, `num(x: float64)`, `text(s: str)` | Constructors, all `-> Json`, below |
| `j.as_int()`, `j.as_float()`, `j.as_str()`, `j.as_bool()`, `j.as_list()`, `j.as_object()` | Typed getters, below |

Like Python, `NaN`, `Infinity` and `-Infinity` are read and written. Unlike Python, a `\u` escape of a lone surrogate is an error, since a Myla string holds UTF-8, and nesting is limited to 200 levels (what every implementation's stack takes: the interpreters run the parser's recursion on their own).

## Building, reading and printing values

The constructors, the getters, paths and the pretty printer came with [[MYLA-332]].

```myla
import std.json as json

fun main() {
    let doc = json.obj([
        ("name", json.text("demo")),
        ("version", json.num(2.0)),
        ("ratio", json.num(0.75)),
        ("tags", json.arr([json.text("a"), json.text("b")])),
        ("owner", json.obj([("emails", json.arr([json.text("ada@example.org")]))])),
    ])
    print(json.pretty(doc))
    match json.at(doc, "owner.emails[0]") {
        Some(v) => print(v.as_str().unwrap_or("not a string"))
        None => print("none")
    }
    print(json.at(doc, "version").and_then((v) => v.as_int()).unwrap_or(0))
    print(json.at(doc, "ratio").and_then((v) => v.as_float()).unwrap_or(0.0))
    print(json.at(doc, "tags[5]").is_none())
    print(json.to_string(json.parse("[1, {\"x\": [true]}]").expect("valid")))
}
// output:
// {
//   "name": "demo",
//   "version": 2,
//   "ratio": 0.75,
//   "tags": [
//     "a",
//     "b"
//   ],
//   "owner": {
//     "emails": [
//       "ada@example.org"
//     ]
//   }
// }
// ada@example.org
// 2
// 0.75
// true
// [1,{"x":[true]}]
```

| Item | Meaning |
| --- | --- |
| `obj(members: [(str, Json)]) -> Json` | `Json.Object(members)` |
| `arr(items: [Json]) -> Json` | `Json.Array(items)` |
| `num(x: float64) -> Json` | An `Int` when `x` is a whole number of size below 2^53 (every such float64 is exact), as JavaScript writes `2.0` as `2`; a `Float` otherwise. A larger integer is `Json.Int(n)`, made directly |
| `text(s: str) -> Json` | `Json.Str(s)` |
| `j.as_int() -> Option<int64>` | The integer of an `Int`; a `Float` such as `1e2` gives none |
| `j.as_float() -> Option<float64>` | The number of a `Float` or an `Int` |
| `j.as_str() -> Option<str>`, `j.as_bool() -> Option<bool>` | The string of a `Str`, the truth value of a `Bool` |
| `j.as_list() -> Option<[Json]>`, `j.as_object() -> Option<[(str, Json)]>` | The items of an `Array`, the members of an `Object` in order |

A path for `at` is a series of steps: a key of an object after a dot, or an index of an array in brackets, as in `a.b[2].c`. The first key has no dot, and a path may start with an index (`[0].name`); "" is the value itself. A key is every byte up to the next `.` or `[`, and finds what `field` finds. `at` gives none when a step finds nothing (a missing key, an index past the end, an object where an array should be) or when the path isn't of that form (`a..b`, `a.`, `[x]`).

`pretty(j, indent)` writes what Python's `json.dumps(j, indent=indent, ensure_ascii=False)` writes: each item or member on a line of its own, indented by `indent` more spaces a level, `": "` after a key, an empty array or object as `[]` or `{}`; an `indent` of 0 or less starts every item on a line without indenting it. A scratch comparison with Python found the same text for 2,000 random values at indents 0, 1, 2 and 4.
