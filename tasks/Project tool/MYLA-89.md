---
id: MYLA-89
title: std.toml - the TOML subset of D73
type: feature
status: done
priority: medium
labels: [stdlib]
---
Step 2 of the project tool ([[MYLA-64]]): parse `myla.toml` and `myla.lock`, the TOML subset of D73 whose grammar is on [[Architecture/Project-tool]], into a value, as `std.json` does for JSON ([[MYLA-79]]).

- [x] `std.toml` in Myla: `enum Toml { Str(str), Int(int64), Bool(bool), Array([Toml]), Table([(str, Toml)]) }` (tables keep their order), `parse(text) -> Result<Toml, TomlError>`, `struct TomlError { msg: str, line: int32, col: int32 }` (columns count characters, from 1), `field(t, key)`
- [x] The subset exactly: tables and dotted headers, bare and quoted keys, basic and literal strings with TOML's escapes, decimal int64 integers with `_`, booleans, string arrays over several lines with comments and a trailing comma, inline tables; the table rules (a key once, a header once, `[a]` after `[a.b]`, inline tables and values closed)
- [x] Everything outside the subset rejected with a message naming it: floats, `inf`/`nan`, dates and times, hex/octal/binary integers, multi-line strings, dotted keys, arrays of tables, arrays of non-strings; integers beyond int64 are "integer out of range"
- [x] Tests against Python's `tomllib`, as `tests/burn/test_json.py` tests `std.json` against `json`
- [x] Both native builds and both interpreters agree
- [x] [[Language/Standard-library]] documents it

## How

- A byte-level recursive-descent parser like `std.json`'s, line by line: a statement (header or key/value) must end its line, comments aside.
- Myla has no references, so the parser can't hold a pointer to the table it fills. It keeps the document as a value, and `insert` rebuilds the path from the root to the table that gets a new key (copy-on-write keeps that cheap for manifests). What each key path names so far (a table opened by a header, a table created on the way, or something closed: a value or an inline table) is kept in a map keyed by the path, which is all the table rules need.
- Messages are its own (`'a' is defined twice`, `table 'a' is defined twice`, `'a' is not a table that can be extended`, …); keys in messages are written as TOML writes them, quoted and escaped when they aren't bare, so a message is one line.
- No `#test` cases in the module, as in `std.fs` ([[MYLA-88]]): the tests are in `tests/unit/test_toml.py` and `tests/burn/test_toml.py`.

## Evidence

- `tests/unit/test_toml.py`: 23 documents using every construct, each compared with `tomllib.loads`; 53 errors with message, line and column (each unsupported construct, each table rule, strings, escapes, integers, line ends, headers), and a check that `tomllib` rejects each of them that isn't outside the subset; `field`. The unit tests were written after the module, so they weren't seen failing first; mutating the module shows they bite (with the duplicate-header rule disabled, the burn corpus reports 2 of 3,000 documents and the unit tests the `[t]`/`[t]` cases).
- `tests/burn/test_toml.py`, on the Python and the self-hosted native builds: 3,000 generated documents of the subset (2,865 valid for `tomllib`, 135 repeat a key or table by chance) and 4,000 broken ones (1,839 rejected by `tomllib`, 2,125 still valid, 36 outside the subset), about 1 MB in all, all agreeing; and 60 documents in both interpreters.
- The corpus found two bugs in the self-hosted interpreter, fixed here with regression programs in `tests/burn/test_selfhost_interp.py`: `idiv` negated the int64 minimum's quotient (`MIN / 10` gave `922337203685477580`), and a destructuring `let (a, b) = f()?` whose `?` returned early tried to destructure the error ("index out of bounds").
