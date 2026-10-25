---
id: MYLA-63
title: Declarative GUI system inspired by SwiftUI
type: feature
status: backlog
priority: low
labels: [gui, library, design]
---
A SwiftUI-like way to build user interfaces: views as values composed from smaller views, state that re-renders what depends on it, as few dependencies as possible.

## What it would need first

- **Talking to a display without libc**: the Wayland wire protocol over a Unix socket with shared-memory buffers (no library needed), or X11 over a socket; or a first target that is simpler, such as a terminal UI or an HTML canvas.
- **Drawing and text**: a software rasteriser, and font loading and shaping, the hardest part without dependencies.
- **Language features**: SwiftUI leans on result builders (a DSL for view trees), property wrappers for state and protocols with associated types. Myla's closures, pipelines and value semantics cover some of it; a builder syntax probably needs user macros or a dedicated feature.
- **An event loop**: overlaps with concurrency ([[MYLA-61]]).
- File descriptors, sockets and `mmap` in the standard library.

## Done when

- [ ] A design sketch (target platform, rendering approach, the view/state model in Myla syntax) on a wiki page
- [ ] A first prototype target chosen
