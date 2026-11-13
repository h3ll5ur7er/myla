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

The matching takes time proportional to the pattern's length times the path's at worst, never exponential: a component is matched with two pointers, where the last `*` takes one more character on a mismatch, and `**` with a table over the pattern's and the path's components. `a*a*a*a*a*b` against 10,000 `a`s takes 36 µs natively (2026-11-07, `f70137a`).

| Function | Result |
| --- | --- |
| `matches(pattern: str, path: str) -> bool` | Whether `path` matches `pattern` |
| `compile(pattern: str) -> Pattern` | The pattern compiled, to match many paths with |
| `Pattern.matches(self, path: str) -> bool` | The same as `matches`, without compiling the pattern again |

## Walking directories

| Function | Result |
| --- | --- |
| `walk(dir: str) -> Result<[str], IoError>` | Every path below the directory `dir`, relative to it, hidden ones included. A directory comes before what it holds, and the names of each directory are sorted by their bytes: `a`, `a/b`, `a-c`, `a.txt`. A symbolic link is listed but not gone into. A directory that isn't there, isn't one or can't be read is an error |
| `walk_with(dir: str, follow_links: bool) -> Result<[str], IoError>` | `walk`, going into links to directories when `follow_links`, but not into a directory the walk is already in: a link back up is listed, and what is below it isn't |
| `glob(pattern: str) -> Result<[str], IoError>` | The paths that match `pattern`, below the working directory, in the order of `walk`. An absolute pattern searches from the root and gives absolute paths |
| `glob_in(dir: str, pattern: str) -> Result<[str], IoError>` | The same below `dir`, the paths relative to it |

`glob_in(dir, pattern)` gives what `walk(dir)` filtered by `matches(pattern, p)` gives, but reads only the directories the pattern can reach. A component without wildcards is looked up rather than listed, so it may be `.` or `..` (`../lib/*.my`); it is found as `walk` lists it, so a symbolic link that names nothing matches its name. A `**` may match no component, so a file before `/**` matches (`notes.txt/**` gives `notes.txt`, [[MYLA-426]]). A directory that isn't there has no matches; one that can't be read is an error. The errors are `std.fs`'s `IoError` ([[Language/Standard-library/Fs]]).

Symbolic links ([[MYLA-363]]): neither `walk` nor a `**` goes into a link to a directory, as bash's globstar doesn't; the link is a path like any other (`**` matches it as the last component). A component that isn't `**` follows a link, as shells do: `la/*` lists what the directory `la` names. `walk_with(dir, true)` follows links, and tells a directory it is already in by its device and file number (`__path_stat`), so a link back up (`d/up -> ..`) is listed and not gone round. Until November 2026 `std.fs` had no way to tell a link, and `walk` went round such a loop until the path held 40 links, Linux's limit: one loop link gave 123 paths, two about 2⁴⁰; now one gives 3. The walk over a tree of 100 directories of 100 files each (10,100 paths) takes 10 to 13 ms natively, and `glob_in` with `**/*7.txt` over it 14 to 16 ms, as before links were told apart (one stat per path, `lstat` now where it was `stat`; 2026-11-09, on a machine that measured 7 and 11 ms earlier).
