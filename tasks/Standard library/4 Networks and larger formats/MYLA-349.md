---
id: MYLA-349
title: "std.yaml: the safe subset"
type: feature
status: done
priority: low
labels: [stdlib, formats, wave-4]
---
Wave 4 of [[Project/Standard-library-roadmap]], roadmap #57. Block and flow maps and lists, scalars (plain, quoted, multi-line), comments; no anchors, no tags, no multiple documents at first. Values are a `Yaml` enum like `Json`.

- **Owns:** `lib/std/yaml.my`, `docs/Language/Standard-library/Yaml.md`
- **Needs:** [[MYLA-341]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [x] The parser and a writer
- [x] Checked against the cases of the YAML test suite that the subset covers
- [x] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [x] Its page below [[Language/Standard-library]], with a doc block that runs

## Done (2026-11-08)

[[lib/std/yaml.my]], the page [[Language/Standard-library/Yaml]], the burn test [[tests/burn/test_yaml.py]].

- **Values:** `enum Yaml { Null, Bool(bool), Int(int64), Float(float64), Str(str), List([Yaml]), Map([(str, Yaml)]) }`, `#derive(Eq)`; map keys are the text of scalars. Getters as `Json`'s (`as_map` for `as_object`), `field`, and `to_json`/`from_json` (the module imports `std.json`).
- **The subset:** block and flow collections, compact nesting, plain/single/double-quoted scalars over several lines with every YAML 1.2 escape, `|` and `>` with indentation and chomping indicators, comments, `---`, `...`, a BOM, LF/CRLF/CR. Plain scalars resolve by the 1.2 core schema (`resolve`, public); an integer outside int64 is a `Float`, as in `std.json`.
- **Left out, each its own error kind:** anchors, aliases, tags, directives, explicit keys, collections as keys, a second document. Repeated keys are refused (`DuplicateKey`). Nesting is limited to 100 levels.
- **Errors (D168):** `YamlError { kind: YamlErrorKind, line, col }` with `message()` and `Format`, 20 kinds; column in characters.
- **Writer:** `to_string`, block style, strings quoted when they would resolve to another type or are YAML 1.1 booleans (`yes`, `no`, `on`, `off`, …), double-quoted with escapes.

## Evidence

- Test first, loosely: the cases were written with the first version of the module; its first run passed 96 of 120 (a tab check that measured the wrong span, escaped line breaks folded to a space, three wrong expectations), then all. The suite's first run found 5 of 402 wrong (a trailing line at the end of the text without its break in a block scalar, tabs in a block scalar's and a flow collection's indentation), fixed in the module.
- `build/myla test lib/std/yaml.my --stdlib lib`: 130/130 interpreted, `--native` 130/130, `--target aarch64-linux` (qemu) 130/130, `--target wasm32-wasi` (Node) 130/130.
- `python3 -m unittest tests.burn.test_yaml` against the yaml-test-suite data release `data-2022-01-17` (402 cases): 198 in the subset give the value of their events with the core schema and read back the same after `to_string`; 98 with a left-out feature are refused naming one of their features; 11 with explicit keys refused with `ExplicitKey`; 1 with a repeated key refused with `DuplicateKey`; 94 of 94 invalid texts refused; 0 wrong. 4,000 mutated suite texts: no crash, 1,697 read, every one read back the same after writing. 25 cases agree between the interpreter and native code.
- `python3 -m unittest tests.burn.test_std_modules tests.burn.test_doc_blocks` after `scripts/bootstrap.sh`: OK.
- Natively, best of five, a 10 MB document of 18,217 records: `parse` 23 MB/s (414 to 451 ms over runs); `std.json` parses the same values as JSON at 30 MB/s; PyYAML's pure-Python `SafeLoader` 0.4 MB/s. `to_string` 11 MB/s, two thirds of it in `std.num.format_float` (callgrind: about 0.5 M instructions per float).

## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]], with a follow-up in [[MYLA-424]]: a whitespace-only block scalar line; raw control characters; the writer's YAML 1.1 protection covers booleans only.

The follow-up is built and in review in [[MYLA-424]] (2026-11-11).
