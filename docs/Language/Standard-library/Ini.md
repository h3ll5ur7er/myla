# std.ini

INI files, read and written ([[MYLA-332]]). The module imports nothing.

```myla
import std.ini as ini

fun main() {
    let text = "; settings\nname = demo\n\n[server]\nhost = example.org\nport: 8080\n\n[paths]\nhome = /srv/demo\n"
    match ini.parse(text) {
        Ok(doc) => {
            print(doc.get("", "name").unwrap_or("?"))
            print(doc.get("server", "port").unwrap_or("80"))
            print(doc.get("server", "user").unwrap_or("nobody"))
            for s in doc.sections() {
                print(f"[{s}] {doc.keys(s).len()} keys")
            }
            var changed = doc
            changed.set("server", "port", "9090")
            changed.set("log", "level", "debug")
            print(ini.write(changed).trim_end())
        }
        Err(e) => print(f"{e}")
    }
    match ini.parse("[server\nhost = x") {
        Ok(_) => print("parsed")
        Err(e) => print(f"{e}")
    }
}
// output:
// demo
// 8080
// nobody
// [server] 2 keys
// [paths] 1 keys
// name = demo
//
// [server]
// host = example.org
// port = 9090
//
// [paths]
// home = /srv/demo
//
// [log]
// level = debug
// 1: a section header without its closing ']' or its name
```

## The dialect

INI has no standard. This module reads the common dialect, close to Python's `configparser` without its interpolation, its continuation lines and its lower-casing of keys. Each line, trimmed of ASCII whitespace, is one of these:

- blank;
- a comment: it starts with `;` or `#`;
- a section header, `[name]`: the name is what is between the brackets, trimmed, and must not be empty;
- a key and its value, split at the first `=` or `:`, both trimmed: `port = 8080` and `port: 8080` are the same, and `url = a=b` gives the key `url` the value `a=b`.

Lines end at LF or CRLF. Keys before the first header belong to the section "". Names are case-sensitive. A value is taken as written: no quotes are removed, there are no escapes, and a `;` or `#` after a value is part of it (`color = #fff`). A section given twice is one section; a key given twice keeps its first place and its last value. Sections and keys keep the order they came in, since maps keep insertion order (D105).

## Reading and changing

| Item | Meaning |
| --- | --- |
| `parse(text: str) -> Result<Ini, IniError>` | The document that `text` holds |
| `new() -> Ini` | A document without sections or keys |
| `struct Ini` | The sections, each a map from its keys to their values; use the methods below |
| `doc.get(section: str, key: str) -> Option<str>` | A key's value; `section` is "" for the keys before the first header |
| `doc.sections() -> [str]` | The names of the sections in order, without "" |
| `doc.keys(section: str) -> [str]` | The keys of a section in order; none if there is no such section |
| `doc.set(section: str, key: str, value: str)` | A `var self` method: sets the value, adding the section and the key at the end if they are new |

`IniError { kind: IniErrorKind, line: int }` names what is wrong and the line, counted from 1 (D168). `e.message()` is what is wrong, `a line without '=' or ':'`, and its `Format` impl writes the line before it, `3: a line without '=' or ':'`. Any text gives a document or an error: a header of any bytes, `[é` too, is `BadSection`, not a runtime error ([[MYLA-420]], the review's H9).

| `IniErrorKind` | Meaning |
| --- | --- |
| `BadSection` | A line that starts with `[` but doesn't end with `]`, or a header without a name |
| `NoSeparator` | A line that is none of the four kinds above |
| `EmptyKey` | A `=` or `:` with no key before it |

## Writing

`write(doc: Ini) -> str` writes the keys of "" first, then each section after a blank line, its header and its keys, every key as `key = value` on a line of its own. `parse` reads back what it writes, but for what the dialect can't hold: a name or a value with a line end or with spaces at an end, a key that holds `=` or `:` or starts with `[`, `;` or `#`, or a section name "". `set` doesn't check them.
