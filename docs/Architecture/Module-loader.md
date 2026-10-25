# Module loader

Modules are a front-end concern only: [[src/myla/loader.py]] turns an entry file and its imports into one flat `Program` whose top-level names are unique, and the checker, interpreter and compiler never see an import. The language rules are on [[Language/Modules]].

[TOC]

## Steps of `link(entry_path, stdlib_root, source_overrides)`

1. **Load.** Starting from the entry file, read, lex and parse each module once (keyed by its real path), and follow its imports depth-first. `source_overrides` replaces a file's text with an in-memory buffer; the language server uses it for unsaved edits.
2. **Module ids.** The entry module's id is empty; every other module's id is its path relative to the project root with every run of other characters replaced by `$` (`geometry$geometry`). The standard library, outside the project, gets an id built from the relative path to it. Two paths that sanitise to the same id are an error.
3. **Exports.** A module exports its `pub` declarations as `("decl", "id$name")`; `pub from` and `pub import … as` re-exports are added in a loop until nothing changes, so chains of re-exports settle.
4. **Bindings.** For each module: its own declarations, plus what its imports bind, `("decl", qualified)` or `("module", id)`. A collision is a module error.
5. **Renaming.** `_Renamer` walks every declaration and rewrites each reference that resolves to a module-level name into its qualified form: type annotations, struct literal names, pattern type names, trait names, bounds and value references. It tracks local variable and type-parameter scopes so shadowed names stay untouched. A field chain whose prefix is a module binding (`geo.manhattan`, `a.b.c.f`) collapses into the qualified name.
6. **Merge.** All modules' declarations (minus imports) are concatenated into one `Program`.

Path resolution (`_resolve_module_path`) uses the leading-dot count: none means the project root, then the stdlib root; one dot the importer's directory; each further dot one level up. The last segment is a file `x.my` or a package `x/x.my`.

## Consequences

- `$` can't appear in source identifiers, so qualified names never collide with user names, the prelude or `Type.method` keys, and they are valid assembly labels.
- Methods need no renaming: their key is the qualified type name.
- Attribute arguments are **not** renamed, so a `#test` in an imported module can't refer to that module's names ([[MYLA-11]]).
- Errors carry no file name ([[MYLA-10]]).

## The self-hosted loader

[[selfhost/loader.my]] is much simpler: it strips import lines and concatenates the modules' text, dependencies first, without qualification or privacy ([[MYLA-30]]).
