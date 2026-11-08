---
id: MYLA-385
title: "#derive(Json), json.encode and json.decode<T>"
type: feature
status: backlog
priority: medium
labels: [stdlib, json, derive]
---
The derive of D172 ([[MYLA-354]]), after [[MYLA-384]].

- [ ] `trait ToJson { fun to_json(self) -> Json }` and `trait FromJson { fun from_json(j: Json) -> Result<Self, JsonError> }` in `std.json`, implemented for the built-in types (integers checked for range on reading, floats, `bool`, `str`, `char`?, lists, `Option`, maps with `str` keys)
- [ ] `#derive(Json)` on structs and enums, generated as source as `#derive(Hash)` is: fields as written; `Option` fields absent when `None`, read from absent or `null`; unknown fields ignored; enums externally tagged
- [ ] `json.encode<T: ToJson>(v) -> str`, `json.decode<T: FromJson>(text) -> Result<T, JsonError>`, with the error's path (`$.items[2].label`)
- [ ] YAML and TOML through their `Json` conversions, one example each
- [ ] Parity programs and the error corpus (a field type that isn't `Json`, a derive on a generic type while MYLA-379 stands)
