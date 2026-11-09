---
id: MYLA-402
title: "std.toml writes TOML"
type: feature
status: review
priority: low
labels: [stdlib, formats, toml]
---
Roadmap row #55 ([[Project/Standard-library-roadmap]]): `std.toml` parses TOML but can't write it. The project tool edits manifests (`myla.toml`) and would use it.

- [x] A writer for `std.toml`'s document type: tables, arrays of tables, inline tables and arrays, strings (basic, with escapes; multi-line where it reads better), integers, floats (`inf`, `nan`), booleans, dates and times as the parser keeps them
- [x] Keys quoted only when they must be, dotted keys and table headers in the parser's order, so `parse(to_string(doc)) == doc` round-trips
- [x] Round-trip cases over the parser's own test documents, and the TOML test suite's valid files where the parser accepts them
- [x] [[Language/Standard-library/Toml]] and the roadmap row

What the first box asks for beyond the document type: `Toml` (D73's subset) has no floats, dates or times, so the writer has none to write; the parser reads no multi-line strings, so the writer writes none (a multi-line string wouldn't read back); and it reads no dotted keys, so tables get headers (`[a.b]`) or are written inline.

## Proposal (the owner decides)

**The writer covers `Toml` as it is; the parser stays D73's subset.** Alternatives: (a) extend `Toml` and the parser to all of TOML 1.0 (floats, dates and times, arrays of tables, multi-line strings, dotted keys, arrays of any values), which changes the enum that [[selfhost/project.my]] and [[tools/lsp/projects.my]] match on and the subset [[Architecture/Project-tool]] specifies, a task of its own; (b) a writer that refuses what `parse` can't read back (an array of tables, an array of other values than strings) with a `Result`. Chosen: `to_string(doc) -> str` writes any `Toml` value as TOML 1.0 writes it (an array of tables as `[[x]]` sections, other arrays inline), which `tomllib` reads as the same value; only what the subset holds reads back through `parse`, and every document `parse` gives does.

## Evidence

- **The API** ([[lib/std/toml.my]], "Writing"): `to_string(doc: Toml) -> str` and `inline_string(v: Toml) -> str`; `Toml` is now `#derive(Eq)`, so `parse(to_string(doc)) == doc` is written as such. A table's key/value pairs under its header, then its tables and arrays of tables as sections; a table that comes before a key/value pair of its table is written inline, so the keys keep the parser's order; a table that holds only tables gets no header of its own (`[git.color]`, no `[git]`). Keys bare when they can be, else basic strings; strings basic with `\" \\ \b \t \n \f \r \u00XX`, or literal (`'C:\dir'`) when that saves escaping a `"` or `\` and no other escape is needed.
- **Tests first.** The cases and test functions were written before the writer: `build/myla test lib/std/toml.my --stdlib lib` stopped with 5 errors (`to_string`, `inline_string` unknown). After: `48/48 passed.`, interpreted and `--native` (3 test functions with exact texts: a manifest, tables inline before a key, arrays of tables; 8 `inline_string` cases; 11 round trips over the page's document, a manifest, a lock file, tables after their sub-tables, quoted and empty keys, int64 limits, literal strings, control characters; the helpers' cases).
- **Burn tests** ([[tests/burn/test_toml.py]]): the driver writes every document `parse` reads and checks `parse(written) == doc`; Python checks that `tomllib` reads the written text as the original's value, keys in order. Over the existing corpus (3000 generated documents of the subset, 4000 broken ones, the interpreter's 60): all pass. A new test writes 2000 random values beyond the subset (arrays of tables, nested, arrays of any values, keys with any characters) and reads them with `tomllib`: all equal, keys in order. A deliberately broken writer (a literal string chosen for a text with a `'`) fails all three: 94 of 3000, 48 of 4000 differ. `python3 -m unittest tests.burn.test_toml`: `Ran 5 tests in 13.7s OK` (one skipped without MYLA_TOML_TEST).
- **toml-test** ([toml-lang/toml-test](https://github.com/toml-lang/toml-test), cloned 2026-11-09): `MYLA_TOML_TEST=<checkout> python3 -m unittest tests.burn.test_toml` runs its 208 valid TOML 1.0 files: 90 read as `tomllib` reads them and written back (`parse` and `tomllib` both read the written text as the same value), 118 refused as outside the subset, 0 wrong. The files aren't vendored, so the test is skipped without a checkout.
- **Docs:** [[Language/Standard-library/Toml]] has a "Writing" section with a doc block that runs (interpreted and natively the same), its two rows in the table, the index row on [[Language/Standard-library]], and row #55 on the roadmap, and the `myla` skill.
- **Suites** (the branch with all three tasks of the lane): `scripts/bootstrap.sh` reaches the byte-identical fixpoint; `scripts/test.sh fast`: 763 tests, the one failure `test_embedded_std` (`selfhost/embedded_std.my` behind `lib/` until the seed commit); `python3 -m unittest tests.burn.test_std_modules tests.burn.test_doc_blocks tests.burn.test_lsp tests.burn.test_toml tests.burn.test_compiler_parity tests.burn.test_selfhost_cases tests.burn.test_error_corpus tests.burn.test_selfhost_checker tests.burn.test_project_commands`: `Ran 733 tests in 491.9s OK (skipped=1)`.

## Comments

- 2026-11-09: the owner chose to extend std.toml to TOML 1.0 and add `#derive(Toml)`: [[MYLA-407]].
