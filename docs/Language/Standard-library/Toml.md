# std.toml

TOML 1.0 documents, read and written ([[MYLA-89]], [[MYLA-402]], [[MYLA-407]]), and typed values through `#derive(Toml)`: strings (basic, literal and both multi-line kinds), integers in decimal, hexadecimal, octal and binary, floats (with `inf` and `nan`), booleans, offset and local date-times, local dates and times, arrays of any values, inline tables, dotted keys, tables and arrays of tables. Until [[MYLA-407]] it read D73's subset of `myla.toml`; the project tool now gets all of TOML and refuses what a manifest has no use for itself ([[Architecture/Project-tool]]). The burn tests compare it with Python's `tomllib` on thousands of random and broken documents and run the toml-test suite: every valid TOML 1.0 file read and written back, every invalid one refused.

```myla
from std.toml import parse, field, Toml, TomlError

fun main() {
    let text = "[server]\nhost = \"example.org\"\nports = [80, 0x1BB]\nratio = 1.5e-1\nstarted = 1979-05-27T07:32:00-08:00\n\n[[user]]\nname = \"ada\"\n\n[[user]]\nname = \"bob\"\nroles.admin = true\n"
    match parse(text) {
        Ok(doc) => {
            match field(doc, "server") {
                Some(server) => {
                    match field(server, "ports") {
                        Some(Toml.Array(ports)) => { print(ports.len()) },
                        _ => { print("no ports") },
                    }
                    match field(server, "started") {
                        Some(Toml.DateTime(d)) => { print(f"{d.date.year} {d.offset.unwrap_or(0)}") },
                        _ => { print("no date") },
                    }
                },
                None => { print("no [server]") },
            }
            match field(doc, "user") {
                Some(Toml.Array(users)) => { print(users.len()) },
                _ => { print("no users") },
            }
        },
        Err(e) => { print(f"{e}") },
    }
    match parse("a = 1\na = 2\n") {
        Ok(doc) => { print("read") },
        Err(e) => { print(f"{e}") },
    }
}
// output:
// 2
// 1979 -480
// 2
// 2:1: 'a' is defined twice
```

| Item | Meaning |
| --- | --- |
| `enum Toml { Str(str), Int(int64), Float(float64), Bool(bool), DateTime(TomlDateTime), Date(TomlDate), Time(TomlTime), Array([Toml]), Table([(str, Toml)]) }` | A TOML value. A table keeps its keys in the order they were defined; an array of tables is an `Array` of `Table`s; the document is a `Table`. `==` compares what they hold, a NaN equal to a NaN, so that a document read back equals itself |
| `struct TomlDate { year: int32, month: int32, day: int32 }` | A local date, `1979-05-27`: the year 1 to 9999, the day within its month |
| `struct TomlTime { hour: int32, minute: int32, second: int32, nanosecond: int32 }` | A local time, `07:32:00.5`: seconds 0 to 59, the fraction cut off after nine digits |
| `struct TomlDateTime { date: TomlDate, time: TomlTime, offset: Option<int32> }` | A date-time: the offset from UTC in minutes (`Some(0)` for `Z`, `Some(-480)` for `-08:00`), `None` for a local one |
| `parse(text: str) -> Result<Toml, TomlError>` | The document's table |
| `struct TomlError { kind: TomlErrorKind, msg: str, line: int32, col: int32, path: str }` | A text that isn't TOML is a `Syntax` error with its line and column (counting from 1, the column in characters) and no path; a value that doesn't fit its type (`decode`) has its path, `$.servers[2].ip`, and a line and column of 0. `message()` and `{e}` (`2:1: 'a' is defined twice`, `$.port: 70000 is out of range for uint16`), as D168 asks |
| `enum TomlErrorKind { Syntax, MissingField, WrongType, OutOfRange, UnknownVariant }` | What is wrong, as `JsonErrorKind` says it ([[Language/Standard-library/Json]]) |
| `field(t: Toml, key: str) -> Option<Toml>` | A table's value for `key`; `None` for a missing key or a value that isn't a table |
| `parse_doc(text: str) -> Result<TomlDoc, TomlError>` | The document's table (`root`) with where each key path was defined, so a program that checks a document can point at what is wrong ([[MYLA-93]]) |
| `key_pos(d: TomlDoc, path: [str]) -> Option<TomlPos>` | Where the key of the key path is (`["dependencies", "geo", "path"]`, also inside an inline table; of a dotted key `geo.path`, the part that names it); for a table, its header (the one that opened it, else the first header or dotted key that implied it); inside an array of tables, the last element's |
| `value_pos(d: TomlDoc, path: [str]) -> Option<TomlPos>` | Where its value is (for a table opened by a header, the header) |
| `struct TomlPos { line: int32, col: int32, end_line: int32, end_col: int32 }` | From `line`:`col` to just before `end_line`:`end_col`, counted like `TomlError`'s position |
| `to_string(doc: Toml) -> str` | The TOML text of the document, a table ([Writing](#writing)); a value that isn't a table as `inline_string` writes it |
| `inline_string(v: Toml) -> str` | The value on one line, as it stands right of `=`: `"text"`, `'C:\dir'`, `42`, `0.1`, `-inf`, `true`, `1979-05-27T07:32:00Z`, `["a", 1]`, `{ x = 1 }` |
| `encode<T: ToToml>(v: T) -> Result<str, TomlError>`, `decode<T: FromToml>(text: str) -> Result<T, TomlError>` | Typed values ([below](#typed-values)) |

## Reading

What the parser holds a document to is TOML 1.0's grammar and its rules on tables, as `tomllib` keeps them:

- **Keys** are bare (`A`–`Z`, `a`–`z`, `0`–`9`, `_`, `-`), basic or literal strings, and may be dotted, `site."google.com" = true`, with white space around the dots. A key is defined once in its table (`'a' is defined twice`). A dotted key defines the tables on its way; those can take more dotted keys in the same section, and a header may open a sub-table of one (`[fruit.apple.texture]` after `apple.color = …`), but not the table itself (`table 'fruit.apple' is defined by dotted keys already`), and a later section can't add to it with dotted keys.
- **Tables:** `[a.b]` creates `a` if it must, and opens `b`; a table is opened by a header once (`table 'a' is defined twice`), and `[a]` may still come after `[a.b]`. `[[a]]` adds a table to the array of tables `a`; the headers and keys after it go to that last element (`[a.b]` is a table of it). An inline table, `{ x = 1, y.z = 2 }`, is complete: nothing adds to it later, as nothing adds to an array (`'a' is not a table that can be extended`).
- **Strings** are UTF-8 (the whole text must be: `invalid UTF-8`). Basic strings take the escapes `\b \t \n \f \r \" \\ \uXXXX \UXXXXXXXX` (a Unicode scalar value); literal strings none. In the multi-line kinds (`"""`, `'''`) a line break right after the opening quotes is left out, a line break is `"\n"` whether the text has `\n` or `\r\n`, one or two quotes may stand before the closing three, and in a basic one a `\` at the end of a line leaves out the white space and line breaks after it. Control characters other than tab are errors, but for line breaks in the multi-line kinds.
- **Integers** are `int64`: decimal, with `+` or `-`, no leading zeros; `0x`, `0o`, `0b` without a sign; `_` between two digits. One beyond `int64` is `integer out of range`, which TOML asks of a parser that can't hold it (`tomllib` reads it as a big integer).
- **Floats** are the correctly rounded `float64` (`std.num.parse_float`): an integer part, then a fraction, an exponent or both (`1e06`, `6.626e-34`, `1_000.5`), or `inf` and `nan` with a sign or none. Too large a number is infinite, as `tomllib` reads it.
- **Dates and times** are RFC 3339's with TOML's freedoms: `T`, `t` or a space between the date and the time, `Z` or `z`, seconds required (TOML 1.0), any number of digits in the fraction (nine kept). A date that isn't one is an error that says why: `the day must be 01 to 28 in 2023-02`, `the second must be 00 to 59` (no leap second, as `tomllib` and [[Language/Standard-library/Time]] have none), `the year must be 0001 to 9999`.
- **Arrays** hold any values, of mixed types, over several lines with comments and a trailing comma.
- **Nesting** is limited to 100 levels of tables and arrays, the document's own table not counted: each table a header or a dotted key goes through, an array of tables (its array and its element), each array and each inline table. A container past them is the syntax error `tables and arrays nested too deeply (more than 100 levels)` at that container, as std.json (200) and std.yaml (100) limit theirs: the parser recurses a level at a time, and the interpreters run it on their own stack. Without the limit 80 KB of nested inline tables took 28 s and 3 GB and 10^5 `[` overflowed the stack ([[MYLA-424]]); a document reads in time linear in its length.

**Why dates and times are structs of their fields.** A program that reads a date wants its year, a time its hour; `==` should say that `1979-05-27 07:32:00Z` and `1979-05-27T07:32:00+00:00` are the same date-time, as TOML says; and the writer can always write a value from its fields, so `parse(to_string(doc)) == doc` holds without the original text. Three variants, not one with optional parts or four: a date-time always has a date and a time, and whether it is local is its `offset`; a lone date or time is its own struct. What the fields lose is the spelling: `.500` is written `.5`, `-00:00` and `+00:00` as `Z`, a space as `T`. The structs are std.toml's own rather than `std.time.DateTime`, which is UTC only and would make every program that imports std.toml (the compiler among them) import std.time.

## Writing

`to_string` writes a document so that `parse` reads it back as the same value, the keys in the same order: `parse(to_string(doc)) == doc` for every `doc` that `parse` gives. A table's key/value pairs come under its header, one a line, then its tables under headers of their own (`[dependencies.geo]`) and its arrays of tables as `[[bin]]` sections, one an element, a blank line before each. A header ends the table above it, so a table that comes before a key/value pair of its table is written inline (`point = { x = 1 }`), which keeps the order; a table that holds only tables gets no header of its own (`[git.color]` without a `[git]` first).

```myla
import std.toml as toml
from std.toml import Toml, TomlDate

fun main() {
    let doc = Toml.Table([
        ("version", Toml.Int(1)),
        ("ratio", Toml.Float(0.25)),
        ("released", Toml.Date(TomlDate { year: 2026, month: 11, day: 9 })),
        ("package", Toml.Table([
            ("name", Toml.Str("geo")),
            ("authors", Toml.Array([Toml.Str("Ada"), Toml.Str("Bob \"B\"")])),
        ])),
        ("dependencies", Toml.Table([
            ("big num", Toml.Table([("path", Toml.Str("C:\\vendor\\big"))])),
        ])),
        ("bin", Toml.Array([Toml.Table([("name", Toml.Str("a"))]), Toml.Table([("name", Toml.Str("b"))])])),
    ])
    let text = toml.to_string(doc)
    print(text)
    match toml.parse(text) {
        Ok(back) => { print(back == doc) },
        Err(e) => { print(e.msg) },
    }
}
// output:
// version = 1
// ratio = 0.25
// released = 2026-11-09
//
// [package]
// name = "geo"
// authors = ["Ada", 'Bob "B"']
//
// [dependencies."big num"]
// path = 'C:\vendor\big'
//
// [[bin]]
// name = "a"
//
// [[bin]]
// name = "b"
//
// true
```

- **Keys** are bare when they can be, else basic strings; the writer writes no dotted keys.
- **Strings** are basic strings, `"…"`, with `\"`, `\\`, `\b`, `\t`, `\n`, `\f`, `\r` and `\u00XX` for the other control characters; a string with a `"` or a `\` that needs no other escape is a literal string, `'…'`, which reads better (`'C:\dir'`). No multi-line strings: a line break is `\n`. A string's bytes are written as they are, so one that isn't UTF-8 makes a text that isn't TOML.
- **Integers** are decimal; **floats** in their shortest form that reads back (`0.1`, `1e+16`, `-0.0`, `inf`, `nan`); **booleans** `true` and `false`; **dates and times** as RFC 3339 writes them, `1979-05-27T07:32:00.5-08:00`, `Z` for a zero offset, the fraction as long as it needs; **arrays** inline, `[a, b]`, unless every element is a table.
- A `Toml` value `parse` never gives, a table with a key twice, is written twice, which TOML refuses.

## Typed values

`#derive(Toml)` on a struct or an enum writes its `impl ToToml` and `impl FromToml` ([[MYLA-407]]), as `#derive(Json)` writes std.json's (D176, after D172 and [[MYLA-385]]): source the checker writes and checks with the program. `toml.encode(v)` and `toml.decode<T>(text)` go through them.

```myla
import std.toml as toml
from std.toml import TomlDateTime

#derive(Toml)
struct Server {
    host: str,
    port: uint16,
    tags: [str],
    backup: Option<str>,
}

#derive(Toml)
enum Mode {
    Off,
    Every(int),
    Window(int, int),
}

#derive(Toml)
struct Config {
    title: str,
    mode: Mode,
    started: TomlDateTime,
    servers: [Server],
}

fun main() {
    let text = "title = \"demo\"\nmode = { Every = 15 }\nstarted = 1979-05-27T07:32:00Z\n\n[[servers]]\nhost = \"a.example\"\nport = 8080\ntags = [\"web\"]\n\n[[servers]]\nhost = \"b.example\"\nport = 8081\ntags = []\nbackup = \"a.example\"\n"
    match toml.decode<Config>(text) {
        Ok(c) => {
            print(f"{c.title}: {c.servers.len()} servers, backup {c.servers[1].backup.unwrap_or("none")}")
            match toml.encode(Config { title: "off", mode: Mode.Off, started: c.started, servers: [] }) {
                Ok(t) => { print(t) },
                Err(e) => { print(f"{e}") },
            }
        },
        Err(e) => { print(f"{e}") },
    }
    match toml.decode<Config>("title = \"t\"\nmode = \"Every\"\nstarted = 2026-11-09T00:00:00Z\nservers = []\n") {
        Ok(c) => { print("read") },
        Err(e) => { print(f"{e}") },
    }
    match toml.decode<Config>("title = \"t\"\nmode = \"Off\"\nstarted = 2026-11-09T00:00:00Z\n[[servers]]\nhost = \"x\"\nport = 70000\ntags = []\n") {
        Ok(c) => { print("read") },
        Err(e) => { print(f"{e}") },
    }
    match toml.encode(Mode.Off) {
        Ok(t) => { print(t) },
        Err(e) => { print(f"{e}") },
    }
}
// output:
// demo: 2 servers, backup a.example
// title = "off"
// mode = "Off"
// started = 1979-05-27T07:32:00Z
// servers = []
//
// $.mode: variant 'Every' of 'Mode' has a payload: write it as { Every = … }
// $.servers[0].port: 70000 is out of range for uint16
// $: expected a table for a TOML document, found a string
```

| Item | Meaning |
| --- | --- |
| `trait ToToml { fun to_toml(self) -> Toml }` | A value's TOML form. Writing never fails |
| `trait FromToml { fun from_toml(t: Toml) -> Result<Self, TomlError> }` | A value read from its TOML form, a function without `self` (D172): `Point.from_toml(t)`, or `T.from_toml(t)` under `T: FromToml` |
| `encode<T: ToToml>(v: T) -> Result<str, TomlError>` | `to_string(v.to_toml())`, or a `WrongType` error when that isn't a table, as a document must be (a number, a list, a variant without payload) |
| `decode<T: FromToml>(text: str) -> Result<T, TomlError>` | `parse`, then `T.from_toml`. The type comes from explicit type arguments, `toml.decode<Config>(text)`, or from where the result goes (D169) |
| `wrong_type(expected: str, found: Toml) -> TomlError` | For an impl written by hand: `expected a version, found the integer 3` at the value |
| `members(t: Toml, name: str) -> Result<[(str, Toml)], TomlError>` | The members of a table; another value is an error naming the type `name` |
| `member<T: FromToml>(fields: [(str, Toml)], name: str) -> Result<T, TomlError>` | The member `name` read as a `T`, its path step added to an error; a missing one is `MissingField` |
| `optional_member<T: FromToml>(fields, name) -> Result<Option<T>, TomlError>` | The same, `None` when the member is absent |

What the derive writes, as `#derive(Json)` does but for what TOML lacks:

- **A struct** is a table of its fields, named as they are written, in their order (as a document, its tables and arrays of tables come under headers, the rest as key/value pairs). An `Option` field is left out when it is `None` and reads back as `None` when absent. Any other field must be there; keys the struct has no field for are ignored.
- **TOML has no null**, so an `Option` is a struct's field and nothing else: an `Option` in a list, a map, an enum's payload or another `Option` has no TOML form, and the derive refuses it, `cannot derive Toml for struct 'Row': field 'cells' has type '[Option<int32>]', which isn't ToToml and FromToml (TOML has no null: an 'Option' can only be a struct's field, left out when 'None')`. There is no `impl ToToml for Option<T>`.
- **An enum** is externally tagged, as in JSON: a variant without payload is its name, `"Off"`; one with one payload a table of one key, `{ Every = 15 }`; one with more a table whose key holds the array of them, `{ Window = [9, 17] }` (TOML 1.0's arrays may mix types). So a variant with a payload is a table, and `encode` makes a document of it (`Every = 15`); a variant without one is a string, which no document is, and `encode` refuses it (`$: expected a table for a TOML document, found a string`), as `encode` of a number or a list. Inside a document every variant has its place.
- **Fields and payloads** must be `ToToml` and `FromToml` themselves (`(a tuple has no TOML form: make it a struct)`, `(a map is a table only with 'str' keys)`). A recursive type works; a generic type derives it bounded per parameter, as [[MYLA-379]] does for `Eq`, `Hash` and `Json`: `#derive(Toml) struct Page<T> { items: [T] }` gives `impl<T: ToToml> ToToml for Page<T>` and `impl<T: FromToml> FromToml for Page<T>`. A type that derives `Toml` can't also write either impl; a program that derives it imports `std.toml` (`cannot derive Toml for 'P': std.toml isn't imported (write 'import std.toml as toml')`); `toml.decode<Point>` of a type without the impls names the derive in its help. A type may derive both formats, `#derive(Json, Toml)`.

The built-in types:

| Type | TOML | Read from |
| --- | --- | --- |
| `int8` … `int64`, `uint8` … `uint32` | an integer | an integer in the type's range (`128` for an `int8` is `OutOfRange`); a float is `WrongType`, as TOML keeps the two apart |
| `uint64` | an integer; above `int64`'s range, which is TOML's, the nearest float: a value that isn't a float64 (not a multiple of 2048 there) comes back as that float's | the same, or a whole float from 2^63 up to below 2^64. An integer beyond `int64` in the text is `integer out of range` |
| `float64`, `float32` | a float, `inf` and `nan` included; a `float32` in its shortest form, `0.1` | a float or an integer; a finite number beyond `float32`'s range is `OutOfRange` |
| `bool`, `str` | `true`/`false`, a string | the same |
| `char` | a string of the one character | a string of exactly one character |
| `TomlDateTime`, `TomlDate`, `TomlTime` | a date-time, a date, a time | the same kind only |
| `[T]` | an array | an array, each item's index in an error's path |
| `[str: V]` | a table, in the map's order | a table |
| `Toml` | itself | anything |

**Errors and paths** are std.json's: `$` the whole value, `.name` a member, `[2]` an element of an array (of tables too), `["a b"]` a key that isn't a name; `{e}` writes `$.servers[0].port: 70000 is out of range for uint16`. A text that isn't TOML is a `Syntax` error with its line and column and no path. An impl by hand writes both impls with the helpers above, as std.json's page shows for JSON.

The impls of the built-in types are trait impls in `std.toml` itself, as std.json's are (D164): only a program that imports `std.toml` has them.

## Tests

[[tests/burn/test_toml.py]] generates TOML 1.0 documents from a seed, every construct above with random spacing, comments and CRLF, and broken ones (a character deleted, inserted or doubled, the text cut short): `parse` must refuse what `tomllib` refuses and read the rest as `tomllib` does, keys in order (3000 documents, 4000 broken ones, natively; 60 interpreted), and what `to_string` writes must read back, with `parse` and `tomllib`, as the original. It also writes 2000 random values (arrays of tables, floats, dates among them) and reads them with `tomllib`. The [toml-test](https://github.com/toml-lang/toml-test) suite's TOML 1.0 files are in [[tests/burn/data/toml_test_1.0.json]] (MIT, its commit named there; `python3 -m tests.burn.test_toml --vendor <checkout>` makes the file again, `MYLA_TOML_TEST=<checkout>` runs a checkout instead): all 208 valid files read as their JSON says and written back, all 509 invalid ones refused (2026-11-09). `lib/std/toml.my`'s `#test` cases cover each construct and error, interpreted, natively and on aarch64.
