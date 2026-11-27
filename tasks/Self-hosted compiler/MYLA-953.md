---
id: MYLA-953
title: "A type named like a prelude trait can't implement it once its module is imported (`impl Format for Format`)"
type: bug
status: todo
priority: medium
labels: [loader, checker, traits]
---
Found by [[MYLA-966]] (std.imageio's `enum Format`). A module with `pub enum Format { … }` and `impl Format for Format { … }` checks on its own; importing it fails:

```myla fragment
// kinds.my
pub enum Format {
    A
    B
}

impl Format for Format {
    fun format(self, spec: str) -> str {
        return "x"
    }
}
```

```myla fragment
// main.my
import .kinds as kinds
from .kinds import Format

fun main() {
    print(Format.A)
}
```

`type error: unknown trait 'kinds.Format' in 'impl kinds.Format for kinds.Format'`: `Renamer.decl` in [[selfhost/loader.my]] resolves the impl's trait name through the module's own names first, so the prelude's trait becomes the module's enum.

- [ ] A failing case in the loader tests first
- [ ] An impl's trait name resolved among traits (the module's, its imports', the prelude's), not among types
- [ ] std.imageio's `Format` gets its `impl Format` (printing `f.name()`)
