# Module loader

Modules are a front-end concern only: [[src/myla/loader.py]] turns an entry file and its imports into one flat `Program` whose top-level names are unique, and the checker, interpreter and compiler never see an import. The language rules are on [[Language/Modules]].

[TOC]

## Steps of `link(entry_path, *, stdlib_root, source_overrides, packages, project_root)`

All keyword arguments are optional; without `packages` and `project_root` the loader behaves as before [[MYLA-92]]. `packages` is a list of (name, directory) pairs, the `--package name=dir` flags (`parse_package_flag` splits one); `project_root` defaults to the entry file's directory.

0. **Packages.** The list is checked first: a package named `std`, a name that isn't an ASCII letter followed by ASCII letters, digits and `_` (or is a keyword), a name given twice, an empty or missing directory are module errors without a position.
1. **Load.** Starting from the entry file, read, lex and parse each module once (keyed by its real path), and follow its imports depth-first, resolving each once (the module keeps its imports' targets). `source_overrides` replaces a file's text with an in-memory buffer; the language server uses it for unsaved edits.
2. **Module ids.** The entry module's id is empty; every other module's id is its path, without `.my`, with every run of other characters replaced by `$`: relative to the stdlib root for the standard library (`std$io`), to a package's directory, after the package's name, for a package (`geo$shapes` for `G/shapes.my`, as if `G` were `geo/` in the project root, so no fetch path or commit appears in a name; the innermost directory wins if they nest), to the project root for the project (`geometry$geometry`), and above the project root with one `up` per level climbed (`up$up$selfhost$tokens`), so `../x.my` and `x.my` never share an id. The rules are the self-hosted loader's (`module_id` in `selfhost/loader.my`), so both toolchains name declarations alike ([[MYLA-81]]); before, the Python loader dropped the `..` and named the standard library by its path from the project. Paths are compared as written: through a symlink, a stdlib module counts as a project module. Two paths that sanitise to the same id are an error.
3. **Exports.** A module exports its `pub` declarations as `("decl", "id$name")`; `pub from` and `pub import … as` re-exports are added in a loop until nothing changes, so chains of re-exports settle.
4. **Bindings.** For each module: its own declarations, plus what its imports bind, `("decl", qualified)` or `("module", id)`. A collision is a module error.
5. **Renaming.** `_Renamer` walks every declaration and rewrites each reference that resolves to a module-level name into its qualified form: type annotations, struct literal names, pattern type names, trait names, bounds and value references. It tracks local variable and type-parameter scopes so shadowed names stay untouched. A field chain whose prefix is a module binding (`geo.manhattan`, `a.b.c.f`) collapses into the qualified name.
6. **Merge.** All modules' declarations (minus imports) are concatenated into one `Program`.

Path resolution (`_resolve_module_path`) uses the leading-dot count: none means the project root, then the stdlib root; one dot the importer's directory; each further dot one level up. The last segment is a file `x.my` or a package `x/x.my`. Without dots the first segment decides: `std` resolves in the stdlib root only (a project `std` is an error); a package's name in its directory only (`_resolve_in_package`: `geo` is `G/geo.my`, `geo.b.c` is `G/b/c.my` or `G/b/c/c.my`), and a project `geo.my` or `geo/` is then an error, `'geo' is a dependency and cannot be shadowed by a project file or directory`, raised at the import like the `std` one; any other name in the project root, then the stdlib root ([[Language/Modules]]).

## Consequences

- `$` can't appear in source identifiers, so qualified names never collide with user names, the prelude or `Type.method` keys, and they are valid assembly labels.
- Methods need no renaming: their key is the qualified type name.
- The arguments and expected outputs of a function's `#test` attributes are renamed like other expressions, in the module's scope (the function's parameters aren't visible there), so a `#test` in an imported module can use that module's consts, structs and enums ([[MYLA-11]]).

## The self-hosted loader

[[selfhost/loader.my]] ports the same steps ([[MYLA-30]]) and returns the linked declarations (`Loaded`), which `build_checker_decls` (checker) type-checks. Its entry points:

| Function | Loads |
| --- | --- |
| `load_program(entry: str, stdlib_root: str) -> Result<Loaded, Report>` | A program without packages, rooted at the entry's directory; `stdlib_root` "" for none |
| `load_program_with(entry: str, stdlib_root: str, overrides: [str: str]) -> Result<Loaded, Report>` | The same with editor buffers (path → text), for the language server |
| `load_program_packages(entry: str, stdlib_root: str, packages: [(str, str)], root: str) -> Result<Loaded, Report>` | With packages, each (name, directory), and the project root `root` ("" for the entry's directory): what the project tool calls in-process, with each package's `dir + "/src"` and `root` `src` for files under `src/` ([[MYLA-94]]) |
| `load_program_opts(entry: str, opts: LoadOptions) -> Result<Loaded, Report>` | With every option: `LoadOptions { stdlib_root: str, packages: [(str, str)], root: str, overrides: [str: str] }`, made by `load_options(stdlib_root)` and changed field by field (the REPL and `build/myla` use it) |

`parse_package_flag(text: str) -> Result<(str, str), Report>` splits a `--package` value at its first `=`; `build/myla` (`run`, `test`, `build`, `repl`), `interp_main` and `gen_main` take the flag, and the last two also `--root <dir>`, so the burn tests (`tests/burn/test_packages.py`) can compare a nested entry with the Python loader's `project_root`. Its differences:

- **Node ids.** The checker keys its side tables by node id, so ids must be unique across the program: each module is parsed with `parse_ids`, which continues numbering where the previous module stopped, and the prelude is parsed last, from the loader's `next_id`. Every module keeps its own line numbers.
- **Immutable AST.** The renamer rebuilds the declarations instead of rewriting them in place; a collapsed `alias.member` chain reuses the ids of the nodes it replaces. Its first error is kept in a field (`err`) rather than returned through every call.
- **Paths.** Paths are normalized textually (`.`, `..`, repeated `/`), not with `realpath`, and existence is probed by reading the file (written before `std.fs` had directory functions, [[MYLA-88]]). So an intermediate segment need not be a directory, a directory `x/` without its root module `x/x.my` reports "cannot resolve", and a project `std` directory isn't reported as shadowing the reserved root: `std.*` simply resolves in the stdlib only. The package checks use `std.fs` (`is_dir` for a package's directory, `exists` for a project `geo` or `geo.my` shadowing a package), so those errors are the Python loader's.
- **Messages** are the Python loader's, printed as the Python CLI prints them; `tests/burn/test_selfhost_codegen.py` (`MODULE_ERRORS`) and, for packages and their errors, `tests/burn/test_packages.py` (`MODULE_ERRORS`, through `gen_main` and `build/myla build`) check they agree.
