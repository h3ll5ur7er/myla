# std.bytes

Strings and bytes ([[MYLA-329]]). A `str` is bytes (D164), so a string becomes a `[uint8]` and back as its bytes are, whatever they are. UTF-8 is checked and built here, where it matters: `is_utf8`, `utf8_error`, `encode_char` and `decode_char`.

```myla
import std.bytes as bytes

fun main() {
    let b = bytes.from_str("né")
    print(b.len())
    print(bytes.is_utf8(b))
    if let Some((c, n)) = bytes.decode_char(b, 1) {
        print(f"{c} in {n} bytes")
    }
    var cut = b
    cut.pop()
    print(bytes.utf8_error(cut).unwrap_or(-1))
    var more = bytes.encode_char('€')
    more.push(33u8)
    print(bytes.to_str(more))
}
// output:
// 3
// true
// é in 2 bytes
// 1
// €!
```

| Function | Result |
| --- | --- |
| `from_str(s: str) -> [uint8]` | The bytes of `s` |
| `to_str(b: [uint8]) -> str` | The bytes as a string, unchanged: they needn't be UTF-8 |
| `is_utf8(b: [uint8]) -> bool` | Whether `b` is UTF-8 |
| `utf8_error(b: [uint8]) -> Option<int>` | The position of the first byte that doesn't start a UTF-8 character, so `b[:i]` is the longest valid prefix; `None` if all of `b` is UTF-8 |
| `encode_char(c: char) -> [uint8]` | The one to four UTF-8 bytes of `c` |
| `decode_char(b: [uint8], at: int) -> Option<(char, int)>` | The character that starts at `b[at]` and its length in bytes; `None` if none starts there or `at` is outside `b` |

UTF-8 is what the Unicode Standard's table 3-7 calls well-formed: the shortest form of each character, no surrogates (U+D800 to U+DFFF), nothing past U+10FFFF. So `[192u8, 128u8]`, an overlong NUL, isn't UTF-8, and neither is `[237u8, 160u8, 128u8]`, the surrogate U+D800. A sequence cut short is wrong at its first byte: `utf8_error([104u8, 226u8, 130u8])` is `Some(1)`.

`from_str` and `to_str` are one allocation and one copy each, on every target and in the interpreter: the primitives `__str_to_bytes` and `__bytes_to_str` ([[MYLA-369]]), which a library module calls (a program's call is the primitive warning, D100). Natively on x86-64 each converts 50 MB in 25 to 26 ms, about 2 GB a second, where `to_str` through a `StringBuilder` a byte at a time took 180 to 209 ms and `from_str` a push a byte 123 to 156 ms; interpreted, 2 MB in 0.07 and 0.12 s, where they took 9.5 and 12 s (2026-11-09).
