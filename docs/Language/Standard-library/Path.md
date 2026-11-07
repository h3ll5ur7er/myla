# std.path

Paths as strings ([[MYLA-326]]). Every function works on the text alone and never looks at the file system. The separator is `/` on every target.

```myla
import std.path as path

fun main() {
    let p = path.join("src", "lib/main.my")
    print(p)
    print(path.parent(p).unwrap_or("none"))
    print(path.stem(p).unwrap_or("none"))
    print(path.with_extension(p, "s"))
    print(path.normalize("src/./lib/../docs/"))
    print(path.relative("src/lib", "docs/Home.md").unwrap_or("none"))
}
// output:
// src/lib/main.my
// src/lib
// main
// src/lib/main.s
// src/docs
// ../../docs/Home.md
```

A path that starts with `/` is absolute. A run of slashes counts as one, and so does a run at the start: `//a` is `/a`, as on Linux (Python's `posixpath.normpath` keeps exactly two leading slashes as they are). `parent` and `file_name` follow Rust's `Path`: trailing slashes don't change them, and a path without one gives None, where Python's `dirname` and `basename` give `""`.

## Joining and splitting

| Function | Result |
| --- | --- |
| `join(a: str, b: str) -> str` | `b` after `a`, with one `/` between them. An absolute `b` replaces `a`, as in Python and Rust: `join("a", "/b")` is `/b`. An empty `a` gives `b`; an empty `b` gives `a/` |
| `join_all(parts: [str]) -> str` | The parts joined one after another; none give `""` |
| `parent(p: str) -> Option<str>` | `p` without its last component: `a/b` gives `a`, `a` gives `""`, `/a` gives `/`. The root, `""` and `.` have none |
| `file_name(p: str) -> Option<str>` | The last component. None for the root, `""`, `.` and a path that ends in `..` |
| `components(p: str) -> [str]` | `/` first for an absolute path, then each name. Empty components and `.` are left out, `..` is kept: `/a/./b/../c` gives `["/", "a", "b", "..", "c"]` |
| `is_absolute(p: str) -> bool` | Whether `p` starts with `/` |

Trailing slashes don't count, and neither does a trailing `.`: `a/b/` and `a/b/.` both have the parent `a` and the file name `b`. Nothing else is resolved: the parent of `a/b/../c` is `a/b/..`.

## Extensions

| Function | Result |
| --- | --- |
| `extension(p: str) -> Option<str>` | What follows the last `.` of the file name, without the dot: `b.tar.gz` gives `gz`, `foo.` gives `""`. A leading dot doesn't start one: `.bashrc` has none, `.b.c` has `c` |
| `stem(p: str) -> Option<str>` | The file name without its extension: `b.tar.gz` gives `b.tar`, `.bashrc` gives `.bashrc` |
| `with_extension(p: str, ext: str) -> str` | `p` with the extension replaced by `ext`, or added; an empty `ext` removes it. A path without a file name stays as it is |

## Resolving `.` and `..`

| Function | Result |
| --- | --- |
| `normalize(p: str) -> str` | `p` with `.` and `..` resolved lexically: `a/./b/../c` is `a/c`. A `..` at the root stays at the root (`/..` is `/`), and a relative path keeps its leading ones (`../a`). Runs of slashes become one, a trailing one goes, and an empty result is `.` |
| `relative(from_dir: str, to: str) -> Option<str>` | The path that leads from the directory `from_dir` to `to`: `relative("a/b", "a/c/d")` is `../c/d`, and `.` when both are the same. Both are normalized first. An absolute `to` from a relative `from_dir` gives `to` normalized |

`normalize` doesn't look at the file system, so it doesn't follow symbolic links: if `a` is a link, `a/..` may not be where `normalize` says. Use it on paths you build, not to find where a path leads.

`relative` gives None when only the file system could tell the answer: a relative `to` from an absolute `from_dir` (the working directory is needed), or a `from_dir` whose `..` climb above where `to` starts (`relative("..", "a")` needs the name of the working directory). Python's `relpath` reads the working directory in both cases.
