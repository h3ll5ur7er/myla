# std.csv

Comma-separated values, read and written after RFC 4180 ([[MYLA-332]]). `parse` and its kin read a text in memory, `stream_reader` the records of a stream one at a time ([[#Reading a stream]]). The module imports `std.io`'s `Read` and `std.ioerror`'s `IoError` (which `std.fs` re-exports).

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

## Reading a stream

`stream_reader(r)` reads the records of any stream `r: R` with `R: Read` (`std.io`, [[MYLA-338]]: a `File`, the standard input's `FdStream`, a `MemoryStream`, a decompressor), one at a time and without reading the stream whole: it holds the record it reads and a chunk of the stream (64 KiB at first, doubled while one record needs more). It is an `Iterator` of `Result<[str], CsvError>`.

```myla
import std.csv as csv
import std.io as io

fun main() {
    let r = csv.stream_reader(io.from_str("id,label\r\n1,plain\r\n2,\"two\nlines\"\r\n3,\"bad\"x\r\n4,never\r\n"))
    for row in r {
        match row {
            Ok(fields) => print(f"{fields.len()}: {fields[0]} [{fields[1]}]")
            Err(e) => print(f"{e}")
        }
    }
}
// output:
// 2: id [label]
// 2: 1 [plain]
// 2: 2 [two
// lines]
// 5:8: a delimiter or a line end expected after '"'
```

| Function or method | Result |
| --- | --- |
| `stream_reader<R: Read>(r: R) -> CsvStreamReader<R>` | A reader of the records of `r` |
| `stream_reader_with<R: Read>(r: R, delim: char) -> CsvStreamReader<R>` | The same with another delimiter, as for `parse_with` |
| `read_record(var self) -> Result<Option<[str]>, CsvError>` | The next record; `None` at the end of the stream |
| `io_error(self) -> Option<IoError>` | Why the stream failed, after an `Io` error |
| `next(var self) -> Option<Result<[str], CsvError>>` | The `Iterator`'s: `Some(Ok(record))` for each, `Some(Err(e))` once if the text is broken or the stream fails, then `None` |

`fill`, a method of `CsvStreamReader`, is the reader's own step, which reads the next chunk, public only because a method can't be private yet ([[MYLA-433]]); a program has no need of it.

It gives what `parse_with` gives, the same records and the same error at the same line and column, wherever its reads end: a case reads 21 texts (every kind of quote, line end, blank line and error) with reads of every size from one byte to the whole text, and again over `io.short_reads`, a stream that gives that many bytes a read whatever the reader asks for (and a scratch comparison of 50,000 random texts over reads of 1, 2, 3 and 5 bytes found no difference). After an error it gives nothing more.

A record is given once its line end is in, without another read first: a stream of lines that come one at a time (a socket, a terminal) gets each record when its line comes. A record that reaches the end of the bytes read so far waits: the reads after it are scanned, each byte once, for the end of the record (a line end outside quotes, or a byte that is an error) and kept aside, and then the record is read again, once ([[MYLA-420]], the review's M17). Before, it was read again after each read, so a long record over short reads took quadratic time: natively, a quoted field of 200,000 bytes over reads of 16 bytes took 1,860 ms, and takes 2 ms now (25,000 bytes: 24 ms, now 7). A line number past 2,147,483,647 stays there (D184). A header row is the first record; map the rest by it as `parse_records` does, if you want maps.

Natively it reads a 50 MB file (359,208 records of nine fields, random ones written by Python's `csv.writer`, about a quarter of the fields quoted) at 93 MB/s in 8.6 MB of memory, where `fs.read_to_string` and `parse` take 97 MB/s and 240 MB (the best of five runs each; peak resident memory). The waiting records didn't change that: another 50 MB file (427,723 records) took 786 to 943 ms with them and 809 to 828 ms before, on a busier machine (2026-11-10).

## Errors

`CsvError { kind: CsvErrorKind, line: int, col: int }` says what is wrong and where (D168): line and column count from 1, the column in characters, as `std.json`'s errors do. `e.message()` says it in words ([[MYLA-405]]), and its `Format` impl writes `line:col: message`, as in the example.

| `CsvErrorKind` | Meaning | `message()` |
| --- | --- | --- |
| `BareQuote` | A `"` inside a field that doesn't start with one | `'"' in an unquoted field` |
| `UnclosedQuote` | A quoted field still open at the end of the text; the position is its opening quote | `a quoted field without its closing '"'` |
| `AfterQuote` | Something other than a delimiter or a line end after a quoted field's closing `"` | `a delimiter or a line end expected after '"'` |
| `FieldCount` | `parse_records`: a record with more fields than the header (at the first extra field) or fewer (at the end of the record) | `a record with another number of fields than the header` |
| `DuplicateName` | `parse_records`: a name the header has twice (at the second) | `a name the header has twice` |
| `Io` | A stream reader's stream failed (at the end of what it read); `io_error()` gives the cause | `the stream failed` |

## Writing

| Function | Result |
| --- | --- |
| `write(rows: [[str]]) -> str` | The records as CSV text, each ended by CRLF |
| `write_with(rows: [[str]], delim: char, line_end: str = "\r\n") -> str` | The same with another delimiter, one `parse_with` takes, and another line end, such as `"\n"` |

A field is quoted only when it must be: when it holds the delimiter, a `"` or a line end, or when it is the only field of its record and empty, since a blank line would be no record. A `"` inside is doubled. This is Python's `csv.writer` with its defaults, and the comparison found the same text for 3,000 random row lists. `parse` reads back what `write` writes, but for a record without fields, which is a blank line.

## Speed

Natively, `parse` reads a 50 MB file of 673,133 records of nine fields (a fifth of them quoted, some with doubled quotes or line ends) at 96 MB/s, best of five runs; Python 3.13's `csv.reader` takes the same text at 42 MB/s.
