---
id: MYLA-30
title: Self-hosted loader concatenates modules as text
type: bug
status: backlog
priority: medium
labels: [selfhost, loader, modules]
---
[[selfhost/loader.my]] removes import lines and concatenates every module's source, dependencies first. There is no name qualification, no privacy and no packages, unlike the Python loader ([[Architecture/Module-loader]]):

- A user function named like a private stdlib helper collides with it: a user `fun collect` clashes with `std.process`'s `collect` → `type-check failed at 130:1`.
- `import x as y` / `y.f()` and package directories (`geometry/geometry.my`) are unsupported, so `examples/modules/main.my` fails: `cannot read module: examples/modules/geometry.my`.
- Each module is lexed and parsed twice.

## Done when

- [ ] The loader links parsed modules the way `src/myla/loader.py` does (unique module ids, `module$name` qualification, `pub` exports, module aliases, packages)
- [ ] `examples/modules` matches the oracle under stage3
- [ ] The fixpoint still holds
