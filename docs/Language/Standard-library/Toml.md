# std.toml

The TOML subset of project manifests and lock files (D73, [[MYLA-89]]): tables and dotted headers, bare and quoted keys, basic and literal strings, decimal `int64` integers, booleans, arrays of strings, inline tables. The grammar is on [[Architecture/Project-tool]]. Every document it accepts means the same in TOML 1.0; the burn tests compare it with Python's `tomllib` on thousands of random and broken documents.

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

What TOML has beyond the subset is an error naming it: "floats are not supported", "dates and times are not supported", "hexadecimal, octal and binary integers are not supported", "multi-line strings are not supported", "dotted keys are not supported", "arrays of tables are not supported", "arrays may only hold strings". An integer beyond `int64` is "integer out of range", as TOML asks of a parser that can't hold it (`tomllib` reads it as a big integer). Other errors are TOML errors, such as `'a' is defined twice`, `table 'a' is defined twice` and `'a' is not a table that can be extended`.
