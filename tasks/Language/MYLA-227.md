---
id: MYLA-227
title: "Generic bodies checked against their trait bounds"
type: feature
status: backlog
priority: low
labels: [language, generics, traits]
---
D104 (6) ([[MYLA-215]]): today a generic function's body is checked per instantiation after monomorphization, so a call of a method its bounds don't provide fails only when someone instantiates it, and the error points at the instantiation. Checking the body once against its bounds gives errors at the definition. Waits until the standard library needs it.

- [ ] A design: what a bound provides (trait methods, operators), how the checker types a body with type parameters
- [ ] Both diagnostics positions documented; [[Language]] pages
