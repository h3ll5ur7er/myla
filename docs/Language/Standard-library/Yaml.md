# std.yaml

The safe subset of YAML 1.2 ([[MYLA-349]]): block and flow mappings and sequences, plain and quoted scalars, literal and folded block scalars, comments. What the subset leaves out (anchors, aliases, tags, directives, a second document) is an error that names it, never a silent misreading. Values are a `Yaml` enum shaped like `std.json`'s `Json`, and convert to and from it.

```myla
import std.yaml as yaml

fun main() {
    let text = "# a service\nname: web\nport: 8080\ndebug: no\ntags: [blue, \"1.0\"]\nmotd: |\n  Hello,\n  world.\n"
    match yaml.parse(text) {
        Ok(doc) => {
            print(yaml.field(doc, "name").and_then((v) => v.as_str()).unwrap_or("?"))
            print(yaml.field(doc, "port").and_then((v) => v.as_int()).unwrap_or(0i64))
            print(yaml.field(doc, "debug").and_then((v) => v.as_str()).unwrap_or("not a string"))
            print(yaml.to_string(doc).trim_end())
        }
        Err(e) => print(f"{e}")
    }
    match yaml.parse("base: &b {x: 1}\n") {
        Ok(_) => print("parsed")
        Err(e) => print(f"{e}")
    }
}
// output:
// web
// 8080
// no
// name: web
// port: 8080
// debug: "no"
// tags:
//   - blue
//   - "1.0"
// motd: "Hello,\nworld.\n"
// 1:7: anchors ('&') are not supported
```

| Item | Meaning |
| --- | --- |
| `enum Yaml { Null, Bool(bool), Int(int64), Float(float64), Str(str), List([Yaml]), Map([(str, Yaml)]) }` | A map keeps its entries in order; its keys are the text of scalars (`1: a` has the key "1"). `#derive(Eq)` |
| `parse(text: str) -> Result<Yaml, YamlError>` | The one document of `text`, below; an empty one is `Null` |
| `to_string(v: Yaml) -> str` | `v` in block style, below |
| `resolve(text: str) -> Yaml` | A plain scalar's value by the core schema, below |
| `field(v: Yaml, key: str) -> Option<Yaml>` | A map's value for `key`; none for a missing key or a value that isn't a map |
| `v.as_int()`, `v.as_float()`, `v.as_str()`, `v.as_bool()`, `v.as_list()`, `v.as_map()` | Typed getters, as `Json`'s: `as_float` takes an `Int` too, `as_map` gives the entries in order |
| `to_json(v: Yaml) -> Json`, `from_json(j: Json) -> Yaml` | The same value as `std.json`'s: a `List` is an `Array`, a `Map` an `Object` |
| `struct YamlError { kind: YamlErrorKind, line: int, col: int }` | What is wrong and where, below |

## The subset

- Block mappings (`key: value`) and sequences (`- item`), nested by indentation, a sequence also at its key's indentation, and compact forms (`- - a`, `- key: v`).
- Flow sequences `[a, b]` and mappings `{a: 1, b}`, over several lines, with a trailing comma; `[k: v]` is a list holding a map of one entry.
- Plain scalars over several lines, single-quoted (`''` is a quote) and double-quoted scalars with every escape of YAML 1.2 (`\n`, `\t`, `\xXX`, `\uXXXX`, `\UXXXXXXXX`, `\N`, `\_`, `\L`, `\P`, a `\` at a line's end, …). Lines fold as YAML folds them: a line break is a space, an empty line a line feed.
- Literal `|` and folded `>` block scalars with an indentation digit and the chomping indicators `-` (strip) and `+` (keep).
- Comments, a leading `---`, a trailing `...`, a byte order mark, an empty key (`: v`), and LF, CRLF or CR line ends.

Left out, each an error of its own kind: anchors (`&a`), aliases (`*a`), tags (`!t`, `!!str`), directives (`%YAML`), explicit keys (`? k`), a collection as a key (`[a]: b`) and a second document. A mapping that repeats a key is refused too, as YAML 1.2 requires; `1: a` and `"1": b` count as the same key, since both keys are "1". The indentation rules are the specification's, so a flow collection's lines, its closing bracket included, are indented more than the block around it, and a tab never indents a block collection. Nesting is limited to 100 levels, as `std.json` limits its own.

## The core schema

A plain scalar (unquoted, not a block scalar) is resolved by YAML 1.2's core schema; a quoted or block scalar is always a `Str`.

| Text | Value |
| --- | --- |
| nothing, `~`, `null`, `Null`, `NULL` | `Null` |
| `true`, `True`, `TRUE`, `false`, `False`, `FALSE` | `Bool` |
| `[-+]?[0-9]+`, `0o[0-7]+`, `0x[0-9a-fA-F]+` | `Int`, or a `Float` outside int64, as in `std.json` |
| `[-+]?(\.[0-9]+\|[0-9]+(\.[0-9]*)?)([eE][-+]?[0-9]+)?`, `[-+]?.inf`, `.nan` (also `.Inf`, `.INF`, `.NaN`, `.NAN`) | `Float` |
| anything else | `Str` |

YAML 1.1, which many parsers still follow (PyYAML among them), reads some of these differently. Here `yes`, `no`, `on`, `off`, `y` and `n` are strings, not booleans; `012` is twelve, not octal ten (YAML 1.2 writes `0o12`); `0b101`, `1_000` and `1:20` (sexagesimal) are strings; `<<` is a plain key, not a merge. `to_string` quotes the strings 1.1 would take for booleans, so its text means the same to both.

## Writing

`to_string(v)` writes a map's entries as `key: value` lines and a list's items as `- item` lines, a nested collection on the lines below its key indented two more spaces, a map or list inside a list in the compact form (`- key: v`), and an empty map or list as `{}` or `[]`. A string is plain when it reads back as the same string: not empty, no leading or trailing space, no indicator first, no `: ` or ` #`, no control character, and not one that would resolve to another type (`"123"`, `"true"`, `"null"`) or that YAML 1.1 reads as a boolean (`"no"`). Any other string is double-quoted, with escapes for `"`, `\`, control characters, C1 controls, U+2028, U+2029 and U+FEFF. Floats are written in their shortest form, and as `.inf`, `-.inf` and `.nan`.

`parse(to_string(v))` gives `v` back, but NaN, which isn't equal to itself, and a map with a repeated key (which only `from_json` can make), which `parse` refuses. A string must be UTF-8 for other parsers to read it.

## Errors

`YamlError { kind: YamlErrorKind, line: int, col: int }`: line and column count from 1, the column in characters, as `std.json`'s errors do. `e.message()` says what is wrong, and its `Format` impl writes `line:col: message`.

| `YamlErrorKind` | Meaning |
| --- | --- |
| `Anchor`, `Alias`, `Tag`, `Directive` | `&a`, `*a`, `!t` or `%YAML`, which the subset leaves out |
| `MultipleDocuments` | A second document, after `---` or `...` |
| `ExplicitKey` | `? key`, which the subset leaves out |
| `ComplexKey` | A flow sequence or mapping used as a key |
| `Tab` | A tab where indentation must be spaces |
| `Indentation` | A line indented where its block doesn't allow it |
| `MissingColon` | A line of a block mapping that isn't `key: value` |
| `InlineCollection` | A block collection on the line of its key: `a: b: c`, `a: - b`, `--- a: b` |
| `MultilineKey` | An implicit key over more than one line |
| `DuplicateKey` | A key the mapping already has (at the second) |
| `UnclosedQuote`, `UnclosedFlow` | A quoted scalar or a flow collection without its end (at its start) |
| `InvalidEscape` | A `\` that isn't an escape, or one of a code point that isn't a Unicode scalar |
| `MissingComma` | Something other than `,` or the closing bracket after an entry of a flow collection |
| `BlockScalarHeader` | Something other than an indentation digit, a chomping indicator and a comment after `\|` or `>` |
| `Unexpected` | A character that can't start or continue anything where it is |
| `TooDeep` | Collections nested more than 100 deep |

## Tests

The module's cases run interpreted, natively, on aarch64 and on wasm32. `tests/burn/test_yaml.py` runs the 402 cases of the YAML test suite's data release `data-2022-01-17` (it clones the release once, or reads `$MYLA_YAML_TEST_SUITE`), taking what each case means from its parse events:

- 198 cases in the subset give the value the events describe, with the core schema, and written by `to_string` read back the same.
- 98 cases that use a left-out feature are refused with the error that names one of their features, 11 with an explicit key (which the events don't show) with `ExplicitKey`, and 1 that repeats a key with `DuplicateKey`.
- The 94 texts that aren't YAML are all refused.
- 4,000 of the suite's texts with a character deleted, inserted or doubled, or cut short, are read or refused without a crash, and what is read is written back the same.

## Speed

Natively, `parse` reads a 10 MB document of 18,217 records (block maps and lists, flow collections, quoted, plain and block scalars, comments) at 23 MB/s, best of five runs; `std.json` parses the same values as JSON at 30 MB/s, and PyYAML's pure-Python `SafeLoader` the YAML at 0.4 MB/s. `to_string` writes it at 11 MB/s, two thirds of that time in `std.num`'s `format_float`.
