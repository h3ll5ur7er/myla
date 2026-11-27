# std.path

Paths as strings ([[MYLA-326]]). Every function works on the text alone and never looks at the file system. The separator is `/` on every target; on Windows `\` is one too, and a path may start with a drive or a UNC share ([see below](#on-windows), D215).

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
| `anchor(p: str) -> str` | Where `p` starts: `/` for an absolute path (a run of slashes is one), `""` for a relative one; on Windows its drive or UNC share and root, `C:\`, `C:`, `\`, `\\srv\share\`. `p` is its anchor, maybe more separators, and its components ([[MYLA-704]]) |

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

## On Windows

On x86-64 Windows std.path reads Windows' paths (D215, [[MYLA-704]]): the loader takes `std/path_windows.my` for `std/path.my` there, as Python's `os.path` is `ntpath` on Windows. A program on any target can import it as `std.path_windows` to work on Windows' paths; it has the same functions with the same types (`tests/burn/test_platform_interface.py` holds it to them). What differs:

- **Separators.** `\` separates components as `/` does: `parent("a\\b")` is `a` (on Linux `""`: `a\b` is one name there).
- **A prefix before the root**, read as Python's `ntpath.splitroot` reads it: a drive (`C:`), or a UNC path's server and share (`\\srv\share`; `\\?\UNC\srv\share`, and `\\?\` or `\\.\` with the name after it, `\\?\C:`, `\\.\pipe`). `//a` is a UNC server there, not the root.
- **Absolute** is a drive with a root (`C:\a`) or a UNC prefix, as `ntpath.isabs`: `\a` is on the working directory's drive and `C:a` in that drive's working directory, neither absolute. `anchor` gives the prefix and root as written (`C:\`, `C:`, `\`, `\\srv\share\`); `components` gives it first.
- **`join`** is `ntpath.join`'s: a `b` with a root replaces `a` but keeps `a`'s drive when it has none of its own (`join("C:\\x", "\\y")` is `C:\y`), one with another drive replaces it all (`join("C:\\x", "D:y")` is `D:y`), one on the same drive, of either case, goes on from `a`; a UNC share and a relative part get a separator between them.
- **What std.path writes is `/`** on every target, which Windows reads: `join`'s separator, and those of what `normalize` and `relative` build (`normalize("C:\\a\\..\\b")` is `C:/b`), so a program builds the same paths everywhere; a prefix stays as written, and what is taken out of a path (`parent`, `file_name`) keeps its own separators. Python's `ntpath` writes `\`.
- **`relative`** compares anchors, a drive's letter of either case alike: from one anchor to another (`C:\` and `D:\`, or `C:\` and `\`) is None; names are compared as written, as the file system isn't asked whether it ignores their case.

A verbatim path (`\\?\C:\…`) is taken as written, as Windows takes it ([[MYLA-798]]): `join` adds to one as Rust's `PathBuf::push` does, the parts split at either separator and joined with `\`, `.` left out and `..` taking away the name before it (`join("\\\\?\\C:\\x", "a/../b")` is `\\?\C:\x\b`), and `normalize` gives one as it is, as Python's `ntpath.normpath` does. std.platform makes a path past `MAX_PATH` verbatim itself before Windows sees it (D261).
