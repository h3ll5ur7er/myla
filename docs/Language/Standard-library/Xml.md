# std.xml

A non-validating XML 1.0 parser, to a tree and as a pull reader, and a writer ([[MYLA-348]]). It checks that a document is well-formed; it reads no DTD and knows no namespaces.

```myla
import std.xml as xml
from std.xml import Event

fun main() {
    let text = "<?xml version=\"1.0\"?>\n<library>\n  <book id=\"1\">Dune &amp; more</book>\n  <book id=\"2\"><title>Solaris</title></book>\n</library>\n"
    match xml.parse(text) {
        Ok(lib) => {
            for b in lib.find_all("book") {
                print(f"{b.attr("id").unwrap_or("?")}: {b.text()}")
            }
        }
        Err(e) => print(f"{e}")
    }
    match xml.parse("<a><b></a>") {
        Ok(_) => print("read")
        Err(e) => print(f"{e}")
    }

    var r = xml.reader("<a><b x='1'/>hi<![CDATA[<raw>]]></a>")
    while true {
        match r.read_event() {
            Ok(Event.Start(name, attrs)) => print(f"start {name}, {attrs.len()} attribute(s)")
            Ok(Event.End(name)) => print(f"end {name}")
            Ok(Event.Text(t)) => print(f"text {t}")
            Ok(Event.CData(t)) => print(f"cdata {t}")
            Ok(Event.Eof) => { break }
            Ok(_) => {}
            Err(e) => {
                print(f"{e}")
                break
            }
        }
    }

    let note = xml.element("note", [("to", "Ada & \"Alan\"")], [xml.Node.Text("1 < 2"), xml.Node.Element(xml.element("sig", [], []))])
    print(xml.to_string(note))
    print(xml.pretty(xml.element("list", [], [xml.Node.Element(note), xml.Node.Comment(" end ")])))
}
// output:
// 1: Dune & more
// 2: Solaris
// 1:7: an end tag that doesn't match the open element
// start a, 0 attribute(s)
// start b, 1 attribute(s)
// end b
// text hi
// cdata <raw>
// end a
// <note to="Ada &amp; &quot;Alan&quot;">1 &lt; 2<sig/></note>
// <list>
//   <note to="Ada &amp; &quot;Alan&quot;">1 &lt; 2<sig/></note>
//   <!-- end -->
// </list>
```

## What it reads

Everything of XML 1.0 (fifth edition) but the DTD: elements, attributes, text, CDATA sections, comments, processing instructions and the XML declaration. The parser checks the well-formedness constraints that don't need a DTD:

- Elements nest, an end tag names the open element, and there is one root element, with only comments, processing instructions and whitespace around it.
- A tag doesn't give an attribute twice, and needs whitespace between attributes. A value is quoted and holds no `<`.
- Names are XML's (fifth edition): a letter, `_` or `:` first, in any script.
- A reference is to a character XML allows (`&#65;`, `&#x20AC;`) or to one of the five predefined entities, `&lt;` `&gt;` `&amp;` `&apos;` `&quot;`. Any other is an error.
- Every character is one XML allows: no control characters but tab, LF and CR, no U+FFFE or U+FFFF, no lone surrogates, and the bytes are well-formed UTF-8.
- A comment holds no `--`, text holds no `]]>`, a processing instruction isn't named `xml` in any case, and the declaration stands at the very start, with a version `1.` and digits, then optionally an encoding and `standalone="yes"` or `"no"`, in that order.

What XML asks of a processor before it parses is done too: CRLF and a lone CR become LF everywhere (2.11), and in an attribute value a literal tab, LF or CR becomes a space (3.3.3; a `&#10;` stays a line end). An attribute's value is normalized no further, as without a DTD every attribute is CDATA.

**The DOCTYPE** is read and skipped: its name, its external id and its internal subset, whose declarations are scanned to their `>` (quotes, comments and processing instructions included) but not used. So no entity is declared, no attribute has a default, and a reference to an entity the subset declares is an `UndefinedEntity` error. A DTD may come later.

**Namespaces** aren't processed: a prefix stays part of the name (`svg:rect`), and `xmlns` attributes are attributes.

**Encodings.** The text is UTF-8, with or without a byte order mark. A declaration may name UTF-8, US-ASCII or ISO-8859-1 (also `latin1`), which is converted to UTF-8 first; any other, or a text in UTF-16, is `UnsupportedEncoding`. Strings are bytes (D164), so the names, text and values the parser gives are UTF-8 bytes.

## The tree

| Item | Meaning |
| --- | --- |
| `parse(text: str) -> Result<Element, XmlError>` | The root element. The declaration, the DOCTYPE and what stands outside the root are dropped |
| `parse_document(text: str) -> Result<Document, XmlError>` | The whole document |
| `parse_stream<R: Read>(r: R) -> Result<Document, XmlError>` | The document a stream holds (`std.io`'s `Read`), read in chunks |
| `struct Element { name: str, attrs: [(str, str)], children: [Node] }` | An element: the attributes in the order written, values with their references replaced |
| `enum Node { Element(Element), Text(str), Comment(str), Pi(str, str) }` | A piece of content; `Pi` holds the target and the data |
| `struct Document { declaration: Option<Declaration>, doctype: Option<str>, prolog: [Node], root: Element, epilog: [Node] }` | `doctype` is what stands between `<!DOCTYPE` and its `>`, trimmed; `prolog` and `epilog` hold the comments and processing instructions before and after the root |
| `struct Declaration { version: str, encoding: str, standalone: str }` | The declaration's values; `encoding` and `standalone` are `""` when it doesn't give them |
| `element(name: str, attrs: [(str, str)], children: [Node]) -> Element` | An element made of its parts (a struct literal of another module's type can't be written) |
| `e.attr(name: str) -> Option<str>` | The value of an attribute |
| `e.elements() -> [Element]` | The child elements |
| `e.find(name: str) -> Option<Element>`, `e.find_all(name: str) -> [Element]` | The first child element of that name, and all of them |
| `e.text() -> str` | The text inside, its descendants' included, in order (Python's `itertext`, joined) |

Text holds the characters with the references replaced. A CDATA section is text: the tree joins it with the text around it, so no two `Text` nodes follow each other and an empty CDATA section is no node. Whitespace between elements is text too, as in Python's `ElementTree`; `pretty` drops it when it writes. Comments and processing instructions inside the root stay in the tree.

## The pull reader

`reader(text)` is an `XmlReader` at the start of a text; `r.read_event()` gives the next `Event`, or the error at the first place the text isn't well-formed. It is a value: keep it in a `var`. It is also an `Iterator<Result<Event, XmlError>>`, which ends before `Eof` and after an error (`for ev in xml.reader(text) { … }`). `parse` builds its tree from these events.

| `Event` | What |
| --- | --- |
| `Declaration(Declaration)` | The XML declaration |
| `Doctype(str)` | The DOCTYPE, as `Document.doctype` holds it |
| `Start(str, [(str, str)])` | A start tag: the name and the attributes. An empty element `<a/>` gives a `Start` and an `End` |
| `End(str)` | An end tag |
| `Text(str)` | Character data, the references replaced; whitespace outside the root gives none |
| `CData(str)` | A CDATA section's content |
| `Comment(str)`, `Pi(str, str)` | A comment, a processing instruction (target and data) |
| `Eof` | The end, after the root; it comes again if asked for |

`stream_reader(r)` is an `XmlStreamReader<R>` over a stream `r` (`std.io`'s `Read`, such as a `File` or a decompressing `std.compress` reader), with the same `read_event` and the same iterator. It reads chunks of 64 KiB, and more while one event needs more. An event a read cut is read again once the bytes after it may end it (a `>` outside an attribute's quotes, a comment's `-->`, a CDATA section's `]]>`, a processing instruction's `?>`, a reference's `;`), or once they at least match what was held back, however few bytes a read gives (a pipe, a socket): so an event whole in the bytes read is given before the reader reads again, which on a pipe whose sender waits for an answer could block, and a long event costs a few passes, not one a read ([[MYLA-460]]: a 1 MB attribute over 16-byte reads takes 21 ms natively, 49 s before). The bytes that might end a DOCTYPE are its every `>`, so one with a long internal subset over short reads is read again at each declaration. A text may come as several `Text` events, split where a chunk ended. An error is given once the stream has ended, at its place in the document (the rest of the stream is read first, as more bytes might have completed what stood at the end of a chunk). A failure of the stream itself is an error of kind `Io`, and `r.io_error() -> Option<IoError>` gives the cause.

`XmlReader`'s `begin`, `start_tag`, `attr_value`, `end_tag`, `close`, `scan_comment`, `scan_pi`, `pi`, `scan_until`, `special_char` and `name_error`, and `XmlStreamReader`'s `fill`, are the readers' own steps, which `read_event` takes, public only because a method can't be private yet ([[MYLA-433]]); a program has no need of them.

## Writing

| Function | Result |
| --- | --- |
| `to_string(e: Element) -> str` | The element as XML text, without a declaration |
| `pretty(e: Element, indent: int = 2) -> str` | The same with each child on a line of its own, indented by `indent` more spaces a level (with 0 or less, not indented) |
| `escape_text(s: str) -> str` | `s` as element text: `&`, `<` and `>` as references, a CR as `&#13;` |
| `escape_attr(s: str) -> str` | `s` as an attribute value in double quotes: `&`, `<`, `>` and `"` as references, a tab, LF and CR as `&#9;`, `&#10;` and `&#13;` |

Attributes are written in double quotes, in their order, and an element without content as `<a/>`. A CR in text and a tab, LF or CR in a value are written as references because a parser would turn them into LF and spaces; so what `to_string` writes, `parse` reads back as the same tree, which the burn test checks for every document it reads. `pretty` writes an element that holds text other than whitespace as `to_string` does, so its text stays as it is (mixed content isn't indented); in the others it drops the whitespace-only text and puts each child on its own line. Names, comments and processing instructions are written as they are: a comment holding `--`, data holding `?>` or a name that isn't one gives text that doesn't parse.

Nesting has no limit in the module: the reader, the tree builder and the writer loop over stacks, not recursions. A document nested a million levels deep is read and written back on x86-64, on aarch64 and on wasm32: the runtime releases such a tree in a bounded stack on every target ([[MYLA-389]]).

## Errors

`XmlError { kind: XmlErrorKind, line: int, col: int }` says what is wrong and where (D168): line and column count from 1, the column in characters, as `std.json`'s and `std.csv`'s errors do; a line ends at LF, CRLF or a lone CR. `e.message()` says it in words, and its `Format` impl writes `line:col: message`, as in the example.

| `XmlErrorKind` | Meaning |
| --- | --- |
| `UnexpectedEnd` | The text ends inside markup or with an element still open (the position is the end) |
| `Expected(str)` | Something else stands where the text says: `'='`, `'>'`, `"a quote"`, `"whitespace"`, … |
| `InvalidChar` | A character XML doesn't allow, or bytes that aren't UTF-8 |
| `InvalidName` | A name expected: a tag's, an attribute's, a processing instruction's |
| `MismatchedTag` | An end tag that doesn't match the open element, or one with none open |
| `DuplicateAttribute` | An attribute given twice (at the second) |
| `InvalidReference` | A `&` that doesn't start a reference, or a character reference to a character XML doesn't allow (`&#0;`) |
| `UndefinedEntity` | A reference to an entity other than the five predefined ones |
| `LtInAttribute` | A `<` in an attribute value |
| `InvalidComment` | A `--` inside a comment |
| `CDataEndInText` | A `]]>` in text |
| `MisplacedDeclaration` | An XML declaration after the start, or a processing instruction named `xml` in another case |
| `InvalidDeclaration` | A declaration without a version, with a malformed value or with its parts out of order |
| `UnsupportedEncoding` | An encoding other than UTF-8, US-ASCII and ISO-8859-1, or UTF-16 |
| `TextOutsideRoot` | Text before or after the root element |
| `MultipleRoots` | A second root element |
| `NoRoot` | A text without an element |
| `MisplacedMarkup` | A DOCTYPE after the start or a second one, or CDATA outside the root |
| `Io` | The stream reader's stream failed |

## Conformance

`tests/burn/test_xml.py` runs every document three ways, by the pull reader, by the tree and by the stream reader fed 1 to 7 bytes at a time, writes James Clark's canonical XML of each, and checks that the three agree:

- The W3C XML conformance suite (xmlts20130923), James Clark's xmltest cases. All 88 not-well-formed standalone cases without a DOCTYPE (`not-wf/sa`) fail; of the 98 with one, 45 fail and the other 53 have their error in the DTD, which the module skips (the suite found one bug: a U+FFFF in an entity value the subset declares wasn't refused). All 53 valid standalone cases (`valid/sa`) whose internal subset declares no entities, attributes or notations give the canonical form of `valid/sa/out/`; of the other 67, 35 do, and the rest need the DTD (an entity, a default or normalized attribute value) or are in UTF-16. The suite is fetched, as the YAML test suite is, not vendored as toml-test is: its licence lets the cases be passed on only as the unmodified archive. The test downloads `xmlts20130923.tar.gz` from the W3C once, checks its SHA-256 and extracts it into `build/xmlts/` (or uses the one `MYLA_XMLTS` names), and is skipped when neither works.
- 2000 generated documents (elements, attributes, the five entities and character references, CR and CRLF line ends, CDATA, comments, processing instructions, the declaration, a DOCTYPE, names in several scripts) give the canonical form Python's expat gives, and `to_string` of each reads back as the same tree.
- 4000 broken ones (a character deleted, inserted or duplicated, bytes that aren't UTF-8, the text cut short) fail where expat fails (3057) and read as expat reads them where it doesn't (943), but for 26 whose declaration has a version such as `11.0` or `1.`: expat takes any version, this module only `1.` and digits, as XML 1.0 has it. Generating them found two bugs: a name followed by a byte that isn't UTF-8 ended the program (a slice can't end there), and an empty CDATA section left an empty `Text` in the tree, which `to_string` didn't write back.

## Tests

The module's 106 cases cover parsing and every kind of error with its position, the tree's methods, the writer and the escapes, and test functions for the pull reader and its iterator, whole documents, ISO-8859-1, bytes that aren't UTF-8, round trips through `to_string` and `pretty`, the stream reader over streams that give 1 to 64 bytes a read (every event as the text reader gives it), a 250,000-byte attribute over reads of 1 to 16 bytes, events given before a stream that fails after them (each kind of markup, cut in pieces of 1 to 64 bytes), a failing stream, nesting and a tag of 41 attributes. They pass interpreted, natively, on aarch64 under qemu and on wasm32 under Node.

## Speed

Natively on x86-64, over a document of 10 MB (36,072 records of an element with three attributes, a title, an empty element with two attributes, a note of a few dozen words with references and non-ASCII letters, and a comment; 613,228 events), against Python 3.13's `xml.etree.ElementTree` (expat, in C). The best of five runs, and of three such sessions on a machine shared with other work, where the runs varied by about a tenth:

| What | Time | Speed |
| --- | --- | --- |
| `parse` (the tree) | 152 ms | 66 MB/s |
| `reader`, every event read | 130 ms | 77 MB/s |
| `stream_reader` over a `File`, every event read | 183 ms | 55 MB/s |
| Python `ElementTree.fromstring` | 271 ms | 37 MB/s |
| Python `XMLPullParser`, start and end events | 404 ms | 25 MB/s |

Most of the time goes to the values an event is made of (a string per name, text and value, a list of attributes), not to scanning: a loop over the bytes alone takes 14 ms. The stream reader copies each chunk once more, into the bytes not yet read.
