---
id: MYLA-23
title: "#derive(Eq) on recursive enums compares box addresses"
type: bug
status: done
priority: medium
labels: [selfhost, codegen, traits]
---
`emit_eq_component` ([[selfhost/codegen.my]], around line 4776) compares boxed payload slots as if they were inline values, so it compares pointers: two structurally equal recursive values (for example two equal linked lists) are `false`.

## Done when

- [x] Boxed components are compared by calling the enum's `eq` on the dereferenced cells
- [x] Differential test with a derived recursive enum: `derived_eq_on_recursive_enums` (a list and a tree; printed `false false true false false` before)
