# std.url

Percent-encoding, query strings and URLs ([[MYLA-329]]), after RFC 3986.

```myla
import std.url as url

fun main() {
    match url.parse("https://ada@[2001:db8::1]:8443/docs/a%20b?q=x+y&lang=en#top") {
        Ok(u) => {
            print(u.scheme)
            print(u.host.unwrap_or("none"))
            print(u.port.unwrap_or(443))
            print(u.path)
            match url.query_decode(u.query.unwrap_or("")) {
                Ok(pairs) => {
                    for p in pairs {
                        print(f"{p.0} = {p.1}")
                    }
                }
                Err(_) => print("bad query")
            }
            print(u.to_str())
        }
        Err(_) => print("not a URL")
    }
    print(url.percent_encode("a b/c", "/"))
    print(url.query_encode([("name", "Ada Lovelace"), ("x", "1&2")]))
}
// output:
// https
// 2001:db8::1
// 8443
// /docs/a%20b
// q = x y
// lang = en
// https://ada@[2001:db8::1]:8443/docs/a%20b?q=x+y&lang=en#top
// a%20b/c
// name=Ada+Lovelace&x=1%262
```

## Percent-encoding and query strings

| Function | Result |
| --- | --- |
| `percent_encode(s: str, safe: str = "") -> str` | `s` with every byte that is neither unreserved nor one of `safe`'s written `%XX`, in upper-case hex |
| `percent_decode(s: str) -> Result<str, UrlError>` | `s` with every `%XX` replaced by its byte, in either case; a `+` stays a `+` |
| `query_encode(pairs: [(str, str)]) -> str` | `key=value` pairs joined by `&`, each part form-encoded: a space as `+`, every other byte but the unreserved ones as `%XX` |
| `query_decode(s: str) -> Result<[(str, str)], UrlError>` | The pairs between the `&`s, empty pieces skipped, each split at its first `=` (the value is "" without one), `+` read as a space and `%XX` decoded |

The unreserved bytes are RFC 3986's: the ASCII letters and digits, `-`, `.`, `_` and `~`. They never need encoding; every other byte is encoded, the bytes of a UTF-8 character one by one (`é` is `%C3%A9`). Decoding gives the bytes as they are, UTF-8 or not, since strings are bytes.

## URLs

`parse(s: str) -> Result<Url, UrlError>` splits a URI reference (RFC 3986's `URI-reference`) into its parts and checks each against the RFC's grammar. It changes nothing: a part stays percent-encoded and in the case it was written in. A relative reference such as `../g?y` parses too, with the scheme "". `Url.to_str()` puts the parts back together; it gives back the text that was parsed, but for an empty port (`http://h:/`), which `parse` reads as none.

| Field | Holds |
| --- | --- |
| `scheme: str` | `https`; "" for a relative reference |
| `user_info: Option<str>` | What comes before `@` in the authority; `None` without an `@` |
| `host: Option<str>` | The host, an IPv6 address without its brackets; `None` without an authority (`mailto:a@b.c`), `Some("")` for an empty one (`file:///etc/hosts`) |
| `port: Option<int>` | The port, 0 to 65535; `None` without one |
| `path: str` | The path, perhaps "" |
| `query: Option<str>` | After `?`, up to `#`; `None` without a `?`. `query_decode` reads a form's pairs from it |
| `fragment: Option<str>` | After `#`; `None` without one |

A host in brackets is an IPv6 address (with a dotted IPv4 address as its last 32 bits allowed, `::ffff:192.0.2.128`) or RFC 3986's `IPvFuture` (`v7.fe80::a+en1`); zone identifiers aren't read. `to_str` puts a host with a `:` in brackets, so an `IPvFuture` host without a `:` loses them.

The tests check `parse` against the examples of RFC 3986 (sections 1.1.2, 3 and 5.4) and read each back with `to_str`:

| Text | Scheme | Host | Port | Path | Query | Fragment |
| --- | --- | --- | --- | --- | --- | --- |
| `ftp://ftp.is.co.za/rfc/rfc1808.txt` | `ftp` | `ftp.is.co.za` | | `/rfc/rfc1808.txt` | | |
| `ldap://[2001:db8::7]/c=GB?objectClass?one` | `ldap` | `2001:db8::7` | | `/c=GB` | `objectClass?one` | |
| `mailto:John.Doe@example.com` | `mailto` | | | `John.Doe@example.com` | | |
| `telnet://192.0.2.16:80/` | `telnet` | `192.0.2.16` | 80 | `/` | | |
| `urn:oasis:names:specification:docbook:dtd:xml:4.1.2` | `urn` | | | `oasis:names:…:4.1.2` | | |
| `foo://example.com:8042/over/there?name=ferret#nose` | `foo` | `example.com` | 8042 | `/over/there` | `name=ferret` | `nose` |
| `g;x?y#s` | | | | `g;x` | `y` | `s` |

## Errors

| Variant | Meaning |
| --- | --- |
| `BadPercent(int)` | A `%` without two hex digits after it |
| `BadChar(int)` | A byte that isn't allowed where it stands, such as a space or a second `#` |
| `BadScheme(int)` | A scheme that is empty or doesn't start with a letter and go on with letters, digits, `+`, `-` and `.` |
| `BadHost(int)` | A host in brackets that has no `]`, isn't an IP literal, or is followed by something other than a port |
| `BadPort(int)` | A port that isn't decimal digits, or is past 65535 |

The position is a byte index in the text: `parse("http://exa mple.com/")` is `Err(UrlError.BadChar(10))`. `UrlError` derives `Eq`; `Url` doesn't, as `Option` isn't `Eq`.
