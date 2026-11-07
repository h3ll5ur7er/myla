---
id: MYLA-319
title: "Decision: the standard library's conventions"
type: chore
status: done
priority: high
labels: [decision, stdlib, wave-1]
---
Wave 1 of [[Project/Standard-library-roadmap]]. The questions the roadmap leaves to the owner, to settle before the first module. The recommendations are the roadmap's assumptions.

1. **Methods or functions.** Operations on built-in types (`str`, `char`, the integers, lists, maps, `Option`, `Result`) are methods. Each lives in a `std` module's `impl` (`impl str` in `std.str`), and a short list of these modules is imported into every program implicitly ([[MYLA-320]]). Everything else is a function of its module (`import std.path as path`, `path.join(a, b)`). This works today with an explicit import: an imported module's `impl str` and `impl<T> [T]` methods are seen in both runners, while a program that doesn't import the module doesn't see them (checked on master `11aeef7`).
2. **Bytes or characters.** Strings are bytes (D21, D42). Searching, splitting and trimming work on bytes, character classes are ASCII, and Unicode comes later (roadmap #10).
3. **Errors.** A function that can fail returns a `Result` with an error enum of its module (`CsvError`, `ParseIntError`), as `IoError` is (D129). `Option` only means "there is none" (`find`).
4. **Names.** Rust's names where Rust has the operation (`split`, `trim_start`, `starts_with`, `sort_by_key`, `unwrap_or`). A method that changes its receiver is a `var self` method (`xs.sort()`), and one that returns a new value has a past participle or a noun (`xs.sorted()`).
5. **Tests.** Every public function has `#test` cases where it has values to compare. Generic functions are tested by test functions (D162), since `#test` can't take a generic function (D116). Every module's own cases run in the interpreter and natively (`myla test --native`), and on aarch64 and wasm32 when the module does I/O.
6. **Docs.** One wiki page per module, `docs/Language/Standard-library/<Module>.md`, with [[Language/Standard-library]] as the index ([[MYLA-325]]).

- **Owns:** `docs/Project/Decisions.md`
- **Needs:** nothing; it can start as soon as its wave does

- [x] The owner's decision on each point, recorded as a D number: D164, the owner's acceptance of all six recommendations (2026-11-07)
- [x] [[Language/Standard-library]] and the `myla` skill updated with the result
