# Modules

Modules are resolved by the loader before type checking ([[Architecture/Module-loader]]). These are the rules of both toolchains (D17, D22, D54, D57, D73, D76); the self-hosted loader differs only in edge cases ([[Architecture/Module-loader]]).

[TOC]

## Files and packages

- A `.my` file is a **module**; a directory is a **package**.
- A package can have a root module named after it: `geometry/geometry.my` is what `import geometry` means. It defines the package's public surface with `pub` imports (there is no implicit re-export).
- A file and a directory with the same name in one folder (`util.my` and `util/`) make an import of that name ambiguous: a module error.
- The **project root** is the directory of the entry file. In a project with a `myla.toml` ([[Architecture/Project-tool]], D73), the project commands load files under `src/` with `src/` as their project root, nested ones included; the loaders take the root as a parameter for that ([[Architecture/Module-loader]]).

## Import forms

```
import a.b.c                 // binds the full path: use a.b.c.member
import a.b.c as c            // binds c
from a.b import x, y as z    // binds x and z
from .sibling import f       // relative to this file's directory
from ..parent.m import g     // one directory up; ... goes two up, and so on
pub from .shapes import Circle         // re-export an item
pub import .geometry.vector as vector  // re-export a module (needs `as`)
```

- Without leading dots, a path is looked up under the project root first, then in the [packages](#packages-dependencies), then in the standard library. `std` is reserved: a project file or folder named `std` is an error.
- `from a.b import c` resolves `c` as a module (`a/b/c.my`) before looking for an item `c` exported by `a.b`.
- Imports must be explicit; there are no wildcards. A name that collides with another name in the module is an error: rename it with `as`.
- Import cycles are allowed.
- A module bound with `import` is used only as `m.member`; it isn't a value. Types and patterns from another module are brought in with `from … import` (dotted type names like `m.Point` aren't supported in type positions).

## Packages (dependencies)

A build can have packages: libraries, each with a name and a directory, given as `--package name=dir` to the commands that compile (`run`, `test`, `build` and `check` of the Python CLI; `run`, `test`, `build`, `check` and `repl` of `build/myla`; D73 (6), D76, [[MYLA-92]]); the project commands of `build/myla` compute them from `myla.toml` ([[Architecture/Project-tool]], [[MYLA-94]]). A package `geo` with directory `G` behaves as if `G` were a directory `geo/` in the project root:

| Import | File |
| --- | --- |
| `import geo` | `G/geo.my`, the package's root module |
| `from geo.shapes import Circle` | `G/shapes.my` |
| `import geo.curves.round as round` | `G/curves/round.my` (or the package root `G/curves/round/round.my`) |

- An import without dots resolves its first segment: `std` in the standard library only; a package's name in that package only; anything else in the project root, then the standard library.
- A project file or directory named like a package (`geo.my` or `geo/` in the project root) is an error when the package is imported: `'geo' is a dependency and cannot be shadowed by a project file or directory`.
- Inside a package, modules import each other relatively (`from .shapes import Circle`): an absolute `import shapes` is looked up in the project being built. Every package is visible to every module of the build, so packages can import each other by name.
- A package can't be named `std`; a name is an ASCII letter, then ASCII letters, digits and `_`, and not a keyword; a name may be given once; the directory must exist. `--package geo` without `=` is an error.
- A package's modules are named as if the directory were `geo/` in the project root (`geo$shapes$Circle`), whatever the directory's path ([[Architecture/Module-loader]]).

```bash
python3 myla.py run app/main.my --package geo=geo/src --package fmt=fmt/src
build/myla build app/main.my --package geo=geo/src --package fmt=fmt/src -o app/app
```

## Visibility

Declarations are private to their file unless marked `pub`: `pub fun`, `pub struct`, `pub enum`, `pub trait`, `pub const`, `pub typealias`. Fields and methods have no visibility of their own: a public struct's fields are readable wherever the struct is, and an `impl` follows its type.

## Example

`examples/modules/` uses each form:

```
examples/modules/
├── main.my             from .geometry import Point, manhattan
│                       from .text import shout
│                       import .geometry as geo      (then geo.manhattan(p))
├── text.my             pub from .text_impl import shout   (a façade re-export)
├── text_impl.my        pub fun shout(…)
└── geometry/
    └── geometry.my     the package root: pub struct Point, pub fun manhattan, private fun abs
```

```bash
python3 myla.py run examples/modules/main.my    # 7, done!, 7
```
