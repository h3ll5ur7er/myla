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
| `struct JsonError { kind: JsonErrorKind, msg: str, line: int32, col: int32, path: str }` | A `Syntax` error of `parse` has Python 3.13's message and position (the column counts characters) and an empty `path`; the others come from decoding ([below](#typed-values)). `e.message()` is `msg`; `{e}` writes `line:col: msg` or `path: msg` |
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

## Typed values

`#derive(Json)` on a struct or an enum writes its `impl ToJson` and `impl FromJson` ([[MYLA-385]], D172); `json.encode(v)` and `json.decode<T>(text)` go through them.

```myla
import std.json as json

#derive(Json)
struct Point {
    x: int,
    y: int,
}

#derive(Json)
enum Shape {
    Empty,
    Circle(Point, float64),
    Polygon([Point]),
}

#derive(Json)
struct Drawing {
    title: str,
    shapes: [Shape],
    tags: [str: int],
    author: Option<str>,
}

fun main() {
    let d = Drawing {
        title: "demo",
        shapes: [Shape.Empty, Shape.Circle(Point { x: 1, y: 2 }, 0.5), Shape.Polygon([Point { x: 0, y: 0 }])],
        tags: ["draft": 1],
        author: None,
    }
    let text = json.encode(d)
    print(text)
    match json.decode<Drawing>(text) {
        Ok(back) => print(back.shapes.len())
        Err(e) => print(f"{e}")
    }
    let p: Result<Point, json.JsonError> = json.decode("{\"x\": 3, \"y\": 4, \"z\": 5}")
    print(p.map((v: Point) => v.x + v.y).unwrap_or(0))
    match json.decode<Drawing>("{\"title\": \"t\", \"shapes\": [\"Empty\", {\"Circle\": [{\"x\": 1}, 2]}], \"tags\": {}}") {
        Ok(back) => print("read")
        Err(e) => print(f"{e}")
    }
}
// output:
// {"title":"demo","shapes":["Empty",{"Circle":[{"x":1,"y":2},0.5]},{"Polygon":[{"x":0,"y":0}]}],"tags":{"draft":1}}
// 3
// 7
// $.shapes[1].Circle[0].y: missing field
```

| Item | Meaning |
| --- | --- |
| `trait ToJson { fun to_json(self) -> Json }` | A value's JSON form. Writing never fails |
| `trait FromJson { fun from_json(j: Json) -> Result<Self, JsonError> }` | A value read from its JSON form, a function without `self` (D172): `Point.from_json(j)`, or `T.from_json(j)` under `T: FromJson` |
| `encode<T: ToJson>(v: T) -> str` | `to_string(v.to_json())` |
| `decode<T: FromJson>(text: str) -> Result<T, JsonError>` | `parse`, then `T.from_json`. The type comes from explicit type arguments, `json.decode<Point>(text)`, or from where the result goes (`let p: Result<Point, JsonError> = json.decode(text)`, D169) |
| `enum JsonErrorKind { Syntax, MissingField, WrongType, OutOfRange, UnknownVariant }` | What is wrong: the text isn't JSON; an object lacks a field; a value of another kind than the type takes (a string for a number, a fraction for an integer, a variant with a payload it hasn't); an integer outside its type's range; a name that isn't one of the enum's variants |
| `wrong_type(expected: str, found: Json) -> JsonError` | For an impl written by hand: `expected a version, found a string` at the value |
| `members(j: Json, name: str) -> Result<[(str, Json)], JsonError>` | The members of an object; another value is an error naming the type `name` |
| `member<T: FromJson>(fields: [(str, Json)], name: str) -> Result<T, JsonError>` | The member `name` (the last of that name, as `field` finds it) read as a `T`, its path step added to an error; a missing one is `MissingField` |
| `optional_member<T: FromJson>(fields, name) -> Result<Option<T>, JsonError>` | The same, `None` when the member is absent or `null` |

What the derive writes:

- **A struct** is an object of its fields, named as they are written, in their order. An `Option` field is left out when it is `None`, and reads back as `None` from an absent member or `null`. Any other field must be there; members the struct has no field for are ignored, and of two members of one name the last counts.
- **An enum** is externally tagged: a variant without payload is its name, `"Empty"`; one with one payload an object of one member, `{"Dot": {"x": 1, "y": 2}}`; one with more an object whose member is the array of them, `{"Circle": [{"x": 1, "y": 2}, 0.5]}`. A variant without payload is read from its string only.
- **Fields and payloads** must be `ToJson` and `FromJson` themselves, or the derive names the one that isn't: `cannot derive Json for struct 'Edge': field 'ends' has type '(int32, int32)', which isn't ToJson and FromJson (a tuple has no JSON form: make it a struct)`. A recursive type works (`struct Tree { kids: [Tree] }`). A type that derives `Json` can't also write either impl, a generic type can't derive it yet ([[MYLA-379]]: `deriving on generic types is not supported yet (Eq, Hash and Json are derived for concrete structs and enums)`), and a program that derives it imports `std.json` (`cannot derive Json for 'P': std.json isn't imported (write 'import std.json as json')`).

The built-in types:

| Type | JSON | Read from |
| --- | --- | --- |
| `int8` … `int64`, `uint8` … `uint32` | a number | an `Int`, or a whole `Float` (`2.0`, `1e3`), in the type's range: `128` for an `int8` is `OutOfRange`, `1.5` `WrongType` |
| `uint64` | a number; above `int64`'s range the nearest float, `1.8446744073709552e+19` | the same, or a whole `Float` below 2^64: the largest values don't come back, as their float is 2^64 |
| `float64`, `float32` | a number; NaN and the infinities `null` | a `Float` or an `Int`; `null` is `WrongType`, a finite number beyond `float32`'s range `OutOfRange`. A `float32` is written in its shortest form, `0.1` and not `0.10000000149011612` |
| `bool`, `str` | `true`/`false`, a string | the same |
| `char` | a string of the one character | a string of exactly one character |
| `[T]` | an array | an array, each item's index in an error's path |
| `[str: V]` | an object, in the map's order | an object, its last member of a key winning |
| `Option<T>` | `null` for `None`, else the value (a field leaves `None` out) | `null` is `None`, so the `Some(None)` of an `Option<Option<T>>` comes back as `None` |
| `Json` | itself | anything |

**Errors and paths.** A decoding error is a `JsonError` whose `path` says where in the document it is: `$` is the whole value, `.name` a member, `[2]` an item of an array, `["a b"]` a member whose key isn't a name. A missing field's path is the field's, `$.items[2].label`, and `{e}` writes `$.items[2].label: missing field`. Its `line` and `col` are 0: decoding works on a `Json` value, which keeps no positions. A text that isn't JSON is a `Syntax` error with its line and column and no path.

**An impl by hand.** A type with a JSON form of its own writes both impls; the helpers give its errors their paths, and a derived type can then have it as a field:

```myla
import std.json as json
import std.num as num
from std.json import Json, JsonError, ToJson, FromJson

// A version written as the string "1.2", by hand.
struct Version {
    major: int64,
    minor: int64,
}

impl ToJson for Version {
    fun to_json(self) -> Json {
        return Json.Str(f"{self.major}.{self.minor}")
    }
}

impl FromJson for Version {
    fun from_json(j: Json) -> Result<Version, JsonError> {
        let parts = str.from_json(j)?.split(".")
        if parts.len() == 2 {
            match (num.parse_int(parts[0]), num.parse_int(parts[1])) {
                (Some(a), Some(b)) => { return Ok(Version { major: a, minor: b }) }
                _ => {}
            }
        }
        return Err(json.wrong_type("a version \"major.minor\"", j))
    }
}

#derive(Json)
struct Package {
    name: str,
    version: Version,
}

fun main() {
    print(json.encode(Package { name: "demo", version: Version { major: 1, minor: 2 } }))
    match json.decode<Package>("{\"name\": \"x\", \"version\": \"one\"}") {
        Ok(p) => print(p.version.major)
        Err(e) => print(f"{e}")
    }
}
// output:
// {"name":"demo","version":"1.2"}
// $.version: expected a version "major.minor", found a string
```

The impls of the built-in types are trait impls in `std.json` itself, not methods of the implicit modules (D164): only a program that imports `std.json`, directly or through another module, has them, and a program that doesn't pays nothing for them. They add about 5 ms to the check of every program that imports it (a hello world: 65 ms before, 71 ms after with the embedded library).

### YAML and TOML

[[Language/Standard-library/Yaml]] converts its values to and from `Json`, so a derived type reads a YAML document, and writes one, through them:

```myla
import std.json as json
import std.yaml as yaml
from std.json import FromJson

#derive(Json)
struct Service {
    name: str,
    port: uint16,
    hosts: [str],
    debug: Option<bool>,
}

fun main() {
    let text = "name: web\nport: 8080\nhosts:\n  - a.example\n  - b.example\n"
    match yaml.parse(text) {
        Ok(doc) => {
            match Service.from_json(yaml.to_json(doc)) {
                Ok(s) => print(f"{s.name} on {s.port}, {s.hosts.len()} hosts, debug {s.debug.unwrap_or(false)}")
                Err(e) => print(f"{e}")
            }
            let back = Service { name: "db", port: 5432, hosts: [], debug: Some(true) }
            print(yaml.to_string(yaml.from_json(back.to_json())).trim())
        }
        Err(e) => print(f"{e}")
    }
}
// output:
// web on 8080, 2 hosts, debug false
// name: db
// port: 5432
// hosts: []
// debug: true
```

[[Language/Standard-library/Toml]] has no conversion of its own (it is the subset `myla.toml` needs, and the compiler imports it): a few lines write one, a table as an object.

```myla
import std.json as json
import std.toml as toml
from std.json import Json, FromJson
from std.toml import Toml

#derive(Json)
struct Package {
    name: str,
    version: str,
    authors: [str],
    edition: Option<int>,
}

#derive(Json)
struct Manifest {
    package: Package,
    dependencies: [str: str],
}

fun toml_to_json(t: Toml) -> Json {
    return match t {
        Toml.Str(s) => Json.Str(s)
        Toml.Int(n) => Json.Int(n)
        Toml.Bool(b) => Json.Bool(b)
        Toml.Array(xs) => Json.Array(xs.map((x: Toml) => toml_to_json(x)))
        Toml.Table(es) => Json.Object(es.map((e: (str, Toml)) => (e.0, toml_to_json(e.1))))
    }
}

fun read(text: str) {
    match toml.parse(text) {
        Ok(doc) => {
            match Manifest.from_json(toml_to_json(doc)) {
                Ok(m) => print(f"{m.package.name} {m.package.version} by {m.package.authors[0]}, {m.dependencies.len()} dependency")
                Err(e) => print(f"{e}")
            }
        }
        Err(e) => print(e.msg)
    }
}

fun main() {
    read("[package]\nname = \"demo\"\nversion = \"0.1.0\"\nauthors = [\"ada\"]\n\n[dependencies]\nhttp = \"1.2\"\n")
    read("[package]\nname = \"x\"\nversion = 2\nauthors = []\n\n[dependencies]\n")
}
// output:
// demo 0.1.0 by ada, 1 dependency
// $.package.version: expected a string, found the number 2
```
