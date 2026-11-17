---
id: MYLA-797
title: "R7-8 XML stream reader: a cut multi-byte character (H10), the quadratic DOCTYPE"
type: bug
status: todo
priority: high
labels: [xml, round-7]
---
Work package of [[Project/Review-2026-11-17]], lane "XML" (section 5). Files: `lib/std/xml.my`. The reproducers are in the review's bundle (`repro-r6/`, with a README per area); each fix turns its reproducer into a test that fails before it. The owner's decisions it builds as the review recommends: none. New tasks it files take ids 857–860.

- [ ] **H10** (high, old remnant): pieces `<s>Gruesse aus K` + the first byte of `ö`, then the rest: `start s`, a blocked read, an error. `repro-r6/library/xml_stream_waits_cut_char.my`. Reopens [[MYLA-460]]
- [ ] The fix made a DOCTYPE quadratic over short reads (200 KB: 9.2 s, 26 ms before)
- [ ] Low: `<log>value [1]\n` holds back `]\n`
