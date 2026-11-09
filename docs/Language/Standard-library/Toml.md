# std.toml

The TOML subset of project manifests and lock files (D73, [[MYLA-89]]), read and written ([[MYLA-402]]): tables and dotted headers, bare and quoted keys, basic and literal strings, decimal `int64` integers, booleans, arrays of strings, inline tables. The grammar is on [[Architecture/Project-tool]]. Every document it accepts means the same in TOML 1.0; the burn tests compare it with Python's `tomllib` on thousands of random and broken documents.

```myla
from std.toml import parse, field, Toml, TomlError

fun main() {
    match parse("[package]\nname = \"geo\"\nauthors = [\"Ada\"]\n") {
        Ok(doc) => {
            match field(doc, "package") {
                Some(pkg) => {
                    match field(pkg, "name") {
                        Some(Toml.Str(name)) => { print(name) },
                        _ => { print("no name") },
                    }
                },
                None => { print("no [package]") },
            }
        },
        Err(e) => { print(format("{}:{}: {}", e.line, e.col, e.msg)) },
    }
}
// output:
// geo
```

| Item | Meaning |
| --- | --- |
| `enum Toml { Str(str), Int(int64), Bool(bool), Array([Toml]), Table([(str, Toml)]) }` | A table keeps its keys in the order they were defined; the document is a `Table` |
| `parse(text: str) -> Result<Toml, TomlError>` | The document's table |
| `struct TomlError { msg: str, line: int32, col: int32 }` | Line and column count from 1, the column in characters |
| `field(t: Toml, key: str) -> Option<Toml>` | A table's value for `key`; `None` for a missing key or a value that isn't a table |
| `parse_doc(text: str) -> Result<TomlDoc, TomlError>` | The document's table (`root`) with where each key path was defined, so a program that checks a document can point at what is wrong ([[MYLA-93]]) |
| `key_pos(d: TomlDoc, path: [str]) -> Option<TomlPos>` | Where the key of the key path is (`["dependencies", "geo", "path"]`, also inside an inline table); for a table, its header (the one that opened it, else the first that implied it) |
| `value_pos(d: TomlDoc, path: [str]) -> Option<TomlPos>` | Where its value is (for a table opened by a header, the header) |
| `struct TomlPos { line: int32, col: int32, end_line: int32, end_col: int32 }` | From `line`:`col` to just before `end_line`:`end_col`, counted like `TomlError`'s position |
| `to_string(doc: Toml) -> str` | The TOML text of the document, a table ([Writing](#writing)); a value that isn't a table as `inline_string` writes it |
| `inline_string(v: Toml) -> str` | The value on one line, as it stands right of `=`: `"text"`, `'C:\dir'`, `42`, `true`, `["a", "b"]`, `{ x = 1 }` |

What TOML has beyond the subset is an error naming it: "floats are not supported", "dates and times are not supported", "hexadecimal, octal and binary integers are not supported", "multi-line strings are not supported", "dotted keys are not supported", "arrays of tables are not supported", "arrays may only hold strings". An integer beyond `int64` is "integer out of range", as TOML asks of a parser that can't hold it (`tomllib` reads it as a big integer). Other errors are TOML errors, such as `'a' is defined twice`, `table 'a' is defined twice` and `'a' is not a table that can be extended`.

## Writing

`to_string` writes a document so that `parse` reads it back as the same value, the keys in the same order: `parse(to_string(doc)) == doc` for every `doc` that `parse` gives (`Toml` is `Eq`). A table's key/value pairs come under its header, one a line, then its tables under headers of their own (`[dependencies.geo]`), a blank line before each. A header ends the table above it, so a table that comes before a key/value pair of its table is written inline (`point = { x = 1 }`), which keeps the order; a table that holds only tables gets no header of its own (`[git.color]` without a `[git]` first).

```myla
import std.toml as toml
from std.toml import Toml

fun main() {
    let doc = Toml.Table([
        ("version", Toml.Int(1)),
        ("package", Toml.Table([
            ("name", Toml.Str("geo")),
            ("authors", Toml.Array([Toml.Str("Ada"), Toml.Str("Bob \"B\"")])),
        ])),
        ("dependencies", Toml.Table([
            ("big num", Toml.Table([("path", Toml.Str("C:\\vendor\\big"))])),
        ])),
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
//
// [package]
// name = "geo"
// authors = ["Ada", 'Bob "B"']
//
// [dependencies."big num"]
// path = 'C:\vendor\big'
//
// true
```

- **Keys** are bare when they can be (`A`–`Z`, `a`–`z`, `0`–`9`, `_`, `-`), else basic strings.
- **Strings** are basic strings, `"…"`, with `\"`, `\\`, `\b`, `\t`, `\n`, `\f`, `\r` and `\u00XX` for the other control characters; a string with a `"` or a `\` that needs no other escape is a literal string, `'…'`, which reads better (`'C:\dir'`). No multi-line strings: the subset doesn't read them. A string's bytes are written as they are, so one that isn't UTF-8 makes a text that isn't TOML (which `parse` still reads back).
- **Integers** are decimal, **booleans** `true` and `false`, **arrays** inline, `[a, b]`.
- **Beyond the subset:** `Toml` can hold what `parse` never gives, an array of other values than strings or an array of tables. `to_string` writes it as TOML 1.0 does, the array inline (`[1, { a = "b" }]`), an array of tables as `[[bin]]` sections, one an element; Python's `tomllib` reads that as the same value, but `parse` refuses it ("arrays of tables are not supported", "arrays may only hold strings"). `Toml` has no floats, dates or times, so neither does the writer. A table with a key twice, which `parse` never gives, is written twice, which TOML refuses.

The burn tests ([[tests/burn/test_toml.py]]) write every document of their corpus that `parse` reads, read it back with `parse` and with `tomllib`, and compare both with the original, keys in order; they also write 2000 random values beyond the subset, arrays of tables among them, and read them with `tomllib`. With `MYLA_TOML_TEST` naming a checkout of [toml-test](https://github.com/toml-lang/toml-test), its 208 valid files of TOML 1.0 run too: 90 read and written back, 118 refused as outside the subset, none wrong (2026-11-09).
