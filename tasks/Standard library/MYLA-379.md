---
id: MYLA-379
title: "Small gaps wave 3 met: == on Option and Result, IoError's Format, #derive on generic types"
type: improvement
status: backlog
priority: low
labels: [language, stdlib]
---
Found by several wave 3 lanes ([[Project/Standard-library-roadmap]]). Each cost a private helper in more than one module.

- [ ] `==` on `Option<T>` and `Result<T, E>` when their payloads are `Eq` (lanes MYLA-341, MYLA-345, MYLA-344, MYLA-343 compare through `match` helpers)
- [ ] `IoError` has no `message()` or `Format` (D168): adding them changes how `f"{e}"` and the test reports show one, so a decision on the text first
- [ ] `#derive(Eq, Hash)` on a generic type is "not supported yet" ([[MYLA-342]]: `Grid<T>` has no `==`)
- [ ] `std.io.copy` reads 4 KiB at a time; a large copy wants a bigger buffer or a size parameter ([[MYLA-339]])
