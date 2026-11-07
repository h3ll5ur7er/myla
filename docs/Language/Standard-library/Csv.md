# std.csv

Comma-separated values, read and written after RFC 4180 ([[MYLA-332]]). The text is in memory; reading from a stream waits for `std.io`'s `Read` trait ([[MYLA-338]]). The module imports nothing.

```myla
import std.csv as csv

fun main() {
    let text = "name,city,note\r\nAda,London,\"wrote \"\"notes\"\", first\"\r\nAlan,\"Wilmslow, UK\",\r\n"
    match csv.parse_records(text) {
        Ok(people) => {
            for p in people {
                print(f"{p["name"]} ({p["city"]}): [{p["note"]}]")
            }
        }
        Err(e) => print(f"{e}")
    }
    match csv.parse("a,b\n\"open") {
        Ok(_) => print("parsed")
        Err(e) => print(f"{e}")
    }
    let out = csv.write_with([["id", "label"], ["1", "plain"], ["2", "with, comma"]], ',', "\n")
    print(out.trim_end())
}
// output:
// Ada (London): [wrote "notes", first]
// Alan (Wilmslow, UK): []
// 2:1: a quoted field without its closing '"'
// id,label
// 1,plain
// 2,"with, comma"
```

## Reading

| Function | Result |
| --- | --- |
| `parse(text: str) -> Result<[[str]], CsvError>` | The records, each a list of its fields |
| `parse_with(text: str, delim: char) -> Result<[[str]], CsvError>` | The same with another delimiter, such as `'\t'` or `';'` |
| `parse_records(text: str) -> Result<[[str: str]], CsvError>` | The records after the first, each a map from the first record's names to its fields, in the header's order; empty for an empty text or one with only the header |
| `parse_records_with(text: str, delim: char) -> Result<[[str: str]], CsvError>` | The same with another delimiter |

The dialect is RFC 4180's, and where the RFC leaves a choice, Go's `encoding/csv` and Python's `csv` with `strict=True` decide it:

- A record is a line of fields split by the delimiter. It ends at CRLF, LF or a lone CR, or at the end of the text. A blank line is no record, and no line end is needed at the end.
- A field that starts with `"` is quoted. It ends at the next lone `"`, and `""` inside it stands for one `"`. It may hold delimiters and line ends, which stay as written (a CRLF inside quotes stays a CRLF). After its closing quote comes a delimiter, a line end or the end of the text.
- A `"` inside a field that doesn't start with one is an error, as RFC 4180 and Go have it; Python keeps it as a character.
- Spaces are part of a field, quoted or not. `parse` takes records with different numbers of fields; `parse_records` doesn't.
- The delimiter must be an ASCII character and neither `"` nor a line end: another one is a runtime error, since it is the program's mistake and not the text's.

The scratch comparison with Python's `csv` module (`strict=True`) on 23,000 random and written texts found the same records or an error for each, except the texts with a bare quote, which this module refuses.

## Errors

`CsvError { kind: CsvErrorKind, line: int, col: int }` says what is wrong and where: line and column count from 1, the column in characters, as `std.json`'s errors do. Its `Format` impl writes `line:col: what`, as in the example.

| `CsvErrorKind` | Meaning |
| --- | --- |
| `BareQuote` | A `"` inside a field that doesn't start with one |
| `UnclosedQuote` | A quoted field still open at the end of the text; the position is its opening quote |
| `AfterQuote` | Something other than a delimiter or a line end after a quoted field's closing `"` |
| `FieldCount` | `parse_records`: a record with more fields than the header (at the first extra field) or fewer (at the end of the record) |
| `DuplicateName` | `parse_records`: a name the header has twice (at the second) |

## Writing

| Function | Result |
| --- | --- |
| `write(rows: [[str]]) -> str` | The records as CSV text, each ended by CRLF |
| `write_with(rows: [[str]], delim: char, line_end: str = "\r\n") -> str` | The same with another delimiter, one `parse_with` takes, and another line end, such as `"\n"` |

A field is quoted only when it must be: when it holds the delimiter, a `"` or a line end, or when it is the only field of its record and empty, since a blank line would be no record. A `"` inside is doubled. This is Python's `csv.writer` with its defaults, and the comparison found the same text for 3,000 random row lists. `parse` reads back what `write` writes, but for a record without fields, which is a blank line.

## Speed

Natively, `parse` reads a 50 MB file of 673,133 records of nine fields (a fifth of them quoted, some with doubled quotes or line ends) at 96 MB/s, best of five runs; Python 3.13's `csv.reader` takes the same text at 42 MB/s.
