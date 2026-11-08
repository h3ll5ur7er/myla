# std.encoding

Bytes as hex and Base64 text, and back ([[MYLA-329]]), after RFC 4648. The bytes are a `[uint8]`; [[Language/Standard-library/Bytes]] turns a string into one and back.

```myla
import std.bytes as bytes
import std.encoding as enc
from std.encoding import EncodingError

fun main() {
    let data = bytes.from_str("Myla!")
    print(enc.hex_encode(data))
    print(enc.base64_encode(data))
    print(enc.base64_url_encode([251u8, 239u8], false))
    match enc.base64_decode("TXlsYSE=") {
        Ok(b) => print(bytes.to_str(b))
        Err(_) => print("not Base64")
    }
    match enc.hex_decode("4d7") {
        Ok(_) => print("hex")
        Err(EncodingError.BadLength(n)) => print(f"odd length {n}")
        Err(_) => print("not hex")
    }
}
// output:
// 4d796c6121
// TXlsYSE=
// --8
// Myla!
// odd length 3
```

| Function | Result |
| --- | --- |
| `hex_encode(b: [uint8]) -> str` | Two lower-case hex digits a byte |
| `hex_decode(s: str) -> Result<[uint8], EncodingError>` | The bytes of hex digits in either case; an odd number of them is `BadLength` |
| `base64_encode(b: [uint8]) -> str` | Standard Base64 (`+` and `/`), padded with `=` to a multiple of four |
| `base64_url_encode(b: [uint8], pad: bool = true) -> str` | URL-safe Base64 (`-` and `_`), without the padding if `pad` is false |
| `base64_decode(s: str) -> Result<[uint8], EncodingError>` | The bytes of standard Base64; the padding is required |
| `base64_url_decode(s: str) -> Result<[uint8], EncodingError>` | The bytes of URL-safe Base64, padded or not |

Decoding is strict, so a text decodes only if it is what encoding gives. Every byte must be of the alphabet: no line breaks, no spaces, no mix of the two alphabets. A padding must be complete (`Zg==`, not `Zg=`) and only at the end. The bits the last character leaves over must be zero: `Zh==` is an error, though it would give the same byte as `Zg==`.

## Errors

The error says what is wrong and where, as a byte position in the text.

| Variant | Meaning |
| --- | --- |
| `BadLength(int)` | A length no encoding gives: an odd number of hex digits, or Base64 with one character after the last group of four. The position is the length |
| `BadChar(int)` | A byte that isn't a digit of the alphabet |
| `BadPadding(int)` | A padding that is missing (in `base64_decode`), short, superfluous or inside the text; the position is where it starts or should start |
| `TrailingBits(int)` | The last character's unused bits aren't zero |

`EncodingError` derives `Eq`. A bad byte is reported before a bad length: `hex_decode("6x6")` is `BadChar(1)`.

## Speed

On x86-64, best of three runs on 100 MB of random bytes: `base64_encode` takes 0.55 s (180 MB a second), `base64_decode` of its 133 MB of text 0.45 s (220 MB of bytes a second), `hex_encode` 0.61 s (160 MB a second) and `hex_decode` of its 200 MB of text 0.73 s (140 MB of bytes a second). The decoders look each digit up in a table, which is more than twice as fast as comparing ranges. The encoders spend most of their time in `StringBuilder.append_byte`, about 3 ns a byte.
