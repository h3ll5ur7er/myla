---
id: MYLA-348
title: "std.xml: a non-validating parser and writer"
type: feature
status: done
priority: low
labels: [stdlib, formats, wave-4]
---
Wave 4 of [[Project/Standard-library-roadmap]], roadmap #56. Elements, attributes, text, entities, CDATA, comments and processing instructions; no DTD and no namespaces at first.

- **Owns:** `lib/std/xml.my`, `docs/Language/Standard-library/Xml.md`
- **Needs:** [[MYLA-341]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [x] A tree parser and a pull reader
- [x] A writer with escaping
- [x] Checked against the well-formedness part of the W3C conformance suite
- [x] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [x] Its page below [[Language/Standard-library]], with a doc block that runs

## Evidence

- **API** ([[Language/Standard-library/Xml]]): `parse(text) -> Result<Element, XmlError>`, `parse_document(text) -> Result<Document, XmlError>`, `parse_stream<R: Read>(r) -> Result<Document, XmlError>`; `Element { name, attrs: [(str, str)], children: [Node] }` with `attr`, `elements`, `find`, `find_all`, `text`; `Node { Element, Text, Comment, Pi }`, `Document`, `Declaration`, `element(name, attrs, children)`. The pull reader `reader(text) -> XmlReader` and `stream_reader<R: Read>(r) -> XmlStreamReader<R>`, each with `read_event() -> Result<Event, XmlError>` and an `Iterator<Result<Event, XmlError>>`; `Event { Declaration, Doctype, Start, End, Text, CData, Comment, Pi, Eof }`. The writer `to_string(e)`, `pretty(e, indent = 2)`, `escape_text(s)`, `escape_attr(s)`. `XmlError { kind: XmlErrorKind, line, col }` (D168) with `message()` and `Format`.
- **Decisions:** a DOCTYPE is read and skipped, internal subset included (its characters checked), so an entity it declares is an `UndefinedEntity` error; no namespaces; CRLF and CR become LF, and attribute values are normalized as CDATA; UTF-8, US-ASCII and ISO-8859-1 (converted), UTF-16 refused; names after the fifth edition. The reader, the tree builder and the writer loop over stacks: natively a million levels of nesting are read and written.
- **Tests first:** the stub cases failed (0/4), then the module passed them. The burn test found three bugs, each fixed with a case: a name followed by a byte that isn't UTF-8 ended the program (a `str` slice can't end inside bytes that aren't UTF-8); an empty CDATA section left an empty `Text`; U+FFFF in an internal subset's literal (xmltest not-wf 175) was taken. A test function caught a stream bug (ISO-8859-1 bytes held back at a chunk's end were dropped) once its piece sizes were varied enough; the holding back went, as an event that a chunk ends inside a character fails and is read again after the next chunk anyway.
- **Module cases:** 98/98 interpreted, natively, on aarch64 under qemu and on wasm32 under Node.
- **Burn test** `tests/burn/test_xml.py` (new), every document read by the pull reader, the tree and the stream reader in pieces of 1 to 7 bytes, compared as canonical XML: the W3C xmltest cases, not-wf/sa 88/88 refused without a DOCTYPE (45/98 with one; the other 53 have their error in the DTD), valid/sa 53/53 canonical inside the subset (35/67 outside it); 2000 generated documents as expat reads them; 4000 broken ones refused (3057) or read (943) as expat does, but for 26 with a version expat doesn't check (`11.0`). 8 to 14 s. The suite is read from `build/xmlts/` or `MYLA_XMLTS`, skipped without it.
- `python3 -m unittest tests.burn.test_std_modules tests.burn.test_doc_blocks` after a bootstrap (fixed point reached): OK.
- **Speed**, natively, best of five, 10 MB of records: `parse` 66 MB/s, `reader` 77 MB/s, `stream_reader` over a `File` 55 MB/s; Python 3.13's `ElementTree.fromstring` 37 MB/s, `XMLPullParser` 25 MB/s.

## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]], with a follow-up in [[MYLA-424]]: the W3C suite isn't in the checkout; one stale sentence.
