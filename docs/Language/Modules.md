# Modules

Modules are resolved by the loader before type checking ([[Architecture/Module-loader]]). These are the rules of the Python toolchain (D17, D22, D54, D57); the self-hosted loader supports less ([[MYLA-30]]).

[TOC]

## Files and packages

- A `.my` file is a **module**; a directory is a **package**.
- A package can have a root module named after it: `geometry/geometry.my` is what `import geometry` means. It defines the package's public surface with `pub` imports (there is no implicit re-export).
- A file and a directory with the same name in one folder (`util.my` and `util/`) make an import of that name ambiguous: a module error.
- The **project root** is the directory of the entry file. There is no manifest.

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

- Without leading dots, a path is looked up under the project root first, then in the standard library. `std` is reserved: a project file or folder named `std` is an error.
- `from a.b import c` resolves `c` as a module (`a/b/c.my`) before looking for an item `c` exported by `a.b`.
- Imports must be explicit; there are no wildcards. A name that collides with another name in the module is an error: rename it with `as`.
- Import cycles are allowed.
- A module bound with `import` is used only as `m.member`; it isn't a value. Types and patterns from another module are brought in with `from … import` (dotted type names like `m.Point` aren't supported in type positions).

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
