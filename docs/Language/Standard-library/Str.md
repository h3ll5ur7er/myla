# std.str

Methods on `str` for searching, splitting, trimming, case and replacing ([[MYLA-321]]). They are in an `impl str`, so a call reads like a built-in one: `line.split(",")`. Every program sees them without an import ([[MYLA-320]]).

```myla
fun main() {
    let text = "name = Ada\r\nlangs = myla, rust\r\n\r\n"
    for line in text.lines() {
        if let Some(i) = line.find(" = ") {
            let key = line[:i].to_upper()
            let values = line[i + 3:].split(", ")
            print(f"{key.pad_end(6, '.')} {values.len()}: {values[0]}")
        }
    }
    print("  a  b ".trim().replace(" ", "+"))
    print(match "v1.2".strip_prefix("v") {
        Some(v) => v
        None => "none"
    })
}
// output:
// NAME.. 1: Ada
// LANGS. 2: myla
// a++b
// 1.2
```

Strings are bytes (D164). A position or a length counts bytes, as `s[i]` and `s.len()` do. Whitespace is ASCII: space, `\t`, `\n`, `\v`, `\f` and `\r`. Case is ASCII too: `to_upper` changes only `a` to `z`, and every other byte stays as it is. The methods take any bytes, not only UTF-8: a piece may start or end inside a character, where a slice `s[a:b]` stops with an error if the character is well-formed (D174).

## Search

| Method | Result |
| --- | --- |
| `find(needle: str) -> Option<int>` | The first position of `needle`; an empty one is found at 0 |
| `rfind(needle: str) -> Option<int>` | The last position; an empty one is found at the end |
| `find_from(needle: str, start: int) -> Option<int>` | The first position at or after `start`; a negative `start` counts as 0, one past the end finds nothing |
| `contains(needle: str) -> bool` | Whether `needle` is in the string |
| `starts_with(prefix: str) -> bool`, `ends_with(suffix: str) -> bool` | Whether the string starts or ends with it |
| `count(needle: str) -> int` | The number of matches that don't overlap: `"aaaa".count("aa")` is 2 |

## Split

| Method | Result |
| --- | --- |
| `split(sep: str) -> [str]` | The pieces between the matches of `sep`, empty ones included: `"a,,b".split(",")` is `["a", "", "b"]`, and `"".split(",")` is `[""]` |
| `splitn(sep: str, n: int) -> [str]` | At most `n` pieces, the last one holding the rest: `"k = v = w".splitn(" = ", 2)` is `["k", "v = w"]` |
| `words() -> [str]` | The runs of text between whitespace, with no empty ones |
| `lines() -> [str]` | The lines, without their `\n` or `\r\n`. A final line ending gives no empty last line, and a lone `\r` doesn't end a line |

An empty separator splits into characters, as `chars()` does, but as strings: `"aé".split("")` is `["a", "é"]`. `join` is a method of `[str]`, in `std.list` ([[MYLA-323]]).

## Trim, case and padding

| Method | Result |
| --- | --- |
| `trim() -> str`, `trim_start() -> str`, `trim_end() -> str` | Without the whitespace at both ends, at the start or at the end |
| `strip_prefix(prefix: str) -> Option<str>` | The rest after `prefix`, or `None` if the string doesn't start with it |
| `strip_suffix(suffix: str) -> Option<str>` | The string before `suffix`, or `None` |
| `to_upper() -> str`, `to_lower() -> str` | With the ASCII letters changed |
| `repeat(n: int) -> str` | The string `n` times; `""` for `n <= 0` |
| `pad_start(width: int, fill: char) -> str`, `pad_end(width: int, fill: char) -> str` | At least `width` characters, with `fill` added in front or behind; a longer string is never cut. The width counts characters, as a format spec's does |

## Replace

| Method | Result |
| --- | --- |
| `replace(old: str, new: str) -> str` | Every match of `old` replaced by `new`, from left to right and without overlaps |
| `replacen(old: str, new: str, n: int) -> str` | The first `n` matches replaced |

An empty `old` matches before every character and at the end, as in Rust and Python: `"abc".replace("", "-")` is `"-a-b-c-"`. `count` counts the same matches, so `s.count(p)` is always the number of places `s.replace(p, q)` changes.
