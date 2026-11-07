# std.glob

Glob patterns, directory walks and the paths that match a pattern ([[MYLA-326]]). Paths are strings with `/` between their components, as in [[Language/Standard-library/Path]].

```myla
import std.glob as glob

fun main() {
    print(glob.matches("src/*.my", "src/main.my"))
    print(glob.matches("*.my", "src/main.my"))
    print(glob.matches("**/*.my", "src/lib/x.my"))
    print(glob.matches("*", ".hidden"))
    let tests = glob.compile("tests/**/test_*.[ch]")
    for p in ["tests/test_a.c", "tests/unit/test_b.h", "tests/unit/b.c"] {
        print(f"{p}: {tests.matches(p)}")
    }
}
// output:
// true
// false
// true
// false
// tests/test_a.c: true
// tests/unit/test_b.h: true
// tests/unit/b.c: false
```

## Patterns

A pattern is matched one component at a time, the components being what the slashes separate. So a `/` in a path is matched only by a `/` in the pattern, and `*` stays inside one name.

| Pattern | Matches |
| --- | --- |
| `*` | Any run of characters, none included |
| `?` | One character (a UTF-8 character, not a byte) |
| `[abc]`, `[a-z]` | One character of the set; a `]` first and a `-` first or last are members |
| `[!abc]`, `[^abc]` | One character outside the set |
| `\c` | The character `c` itself: `\*` is a `*` |
| `**` | A whole component that is `**`: any number of components, none included. `a/**/z` matches `a/z` and `a/b/c/z`; inside a name, `**` is `*` |
| anything else | Itself |

As in shells, a name that starts with `.` is matched only by a component that starts with a literal `.`: `*`, `?` and a set don't match its first character, and `**` doesn't go through such a directory. So `*` doesn't match `.hidden`, `.*` does, and `**/*.my` doesn't match `.git/x.my`. A `[` without its `]` is literal, and so is a `\` at the end.

Both the pattern and the path must be absolute, or both relative. Empty components don't count, so `a//b/` is `a/b`; `.` and `..` are names like any other (normalize with `std.path` first if you need them resolved).

The matching takes time proportional to the pattern's length times the path's at worst, never exponential: a component is matched with two pointers, where the last `*` takes one more character on a mismatch, and `**` with a table over the pattern's and the path's components. `a*a*a*a*a*b` against 10,000 `a`s takes 36 µs natively.

| Function | Result |
| --- | --- |
| `matches(pattern: str, path: str) -> bool` | Whether `path` matches `pattern` |
| `compile(pattern: str) -> Pattern` | The pattern compiled, to match many paths with |
| `Pattern.matches(self, path: str) -> bool` | The same as `matches`, without compiling the pattern again |

## Walking directories

| Function | Result |
| --- | --- |
| `walk(dir: str) -> Result<[str], IoError>` | Every path below the directory `dir`, relative to it, hidden ones included. A directory comes before what it holds, and the names of each directory are sorted by their bytes: `a`, `a/b`, `a-c`, `a.txt`. A directory that isn't there, isn't one or can't be read is an error |
| `glob(pattern: str) -> Result<[str], IoError>` | The paths that match `pattern`, below the working directory, in the order of `walk`. An absolute pattern searches from the root and gives absolute paths |
| `glob_in(dir: str, pattern: str) -> Result<[str], IoError>` | The same below `dir`, the paths relative to it |

`glob_in(dir, pattern)` gives what `walk(dir)` filtered by `matches(pattern, p)` gives, but reads only the directories the pattern can reach. A component without wildcards is looked up rather than listed, so it may be `.` or `..` (`../lib/*.my`). A directory that isn't there has no matches; one that can't be read is an error. The errors are `std.fs`'s `IoError` ([[Language/Standard-library/Fs]]).

`std.fs` can't tell a symbolic link from what it names: `is_dir` follows links, and there is no `lstat`. So `walk` and `glob` go into a link to a directory as into the directory. A link back to a directory above it is gone round until the path holds 40 links, Linux's limit, where `is_dir` stops seeing a directory: `d/up -> ..` gives `d/up/d/up/…` 40 times over. Two such links give 2⁴⁰ paths, so don't walk a tree with links that loop until `std.fs` can tell a link ([[MYLA-326]] names the gap). The walk over a tree of 100 directories of 100 files each (10,100 paths) takes 7 ms natively, and `glob_in` with `**/*7.txt` over it 11 ms.
