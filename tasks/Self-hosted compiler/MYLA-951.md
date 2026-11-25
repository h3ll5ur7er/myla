---
id: MYLA-951
title: "List slices copy element by element: `a[1:]` of 36 MB takes 95 ms natively"
type: improvement
status: todo
priority: low
labels: [performance, native, images]
---
Found by [[MYLA-935]]: a slice of a `[uint8]` copies one element at a time, about 95 ms for `a[1:]` of 36 MB natively, about 35 ms of std.png's decode of a 12-megapixel image (slicing IDAT data out of the file). Codecs slice their input everywhere. Related to [[MYLA-949]] (`list.filled`).

- [ ] Measured first: a slice of 36 MB of `uint8` and of `int64`
- [ ] A slice of plain elements (no heap pointers inside) copied as one block, as `__str_to_bytes` copies; elements that hold heap cells keep the retaining loop
- [ ] Measured again
