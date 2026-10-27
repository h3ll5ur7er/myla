---
id: MYLA-63
title: Declarative GUI system inspired by SwiftUI
type: feature
status: backlog
priority: low
labels: [gui, library, design]
---
A SwiftUI-like way to build user interfaces: views as values composed from smaller views, state that re-renders what depends on it, as few dependencies as possible.

> [!NOTE]
> **On hold** (2026-10-25) until the rest fits: correct toolchains, the IR, concurrency ([[MYLA-61]]) and a project tool ([[MYLA-64]]) come first.

## Graphics without libc

- **Software rendering is fully possible without libc**: draw into memory and hand it to the display through a Wayland `wl_shm` buffer or X11 shared memory (both plain socket protocols plus `mmap`), or directly to the screen through the kernel's DRM/KMS "dumb buffer" ioctls on `/dev/dri/card0` (no display server, driver-independent).
- **OpenGL and Vulkan are not practical without C libraries.** They are C APIs whose implementation is the GPU vendor's user-space driver (Mesa or NVIDIA's), loaded as shared libraries that depend on libc. The kernel interface underneath (DRM ioctls and command buffers) is different for every GPU family; talking to it directly means writing a GPU driver.
- So hardware acceleration needs a **C FFI**: the System V calling convention (Myla's internal convention is stack-based), C struct layout, callbacks, and a dynamically linked executable (an interpreter `/lib64/ld-linux-x86-64.so.2` and `-lvulkan`). Myla's own runtime can stay libc-free while the process loads libc indirectly through the driver, which is the approach Go takes. macOS and Windows require system libraries for any graphics anyway.

## What it would need first

- **Talking to a display without libc**: the Wayland wire protocol over a Unix socket with shared-memory buffers (no library needed), or X11 over a socket; or a first target that is simpler, such as a terminal UI or an HTML canvas.
- **Drawing and text**: a software rasteriser, and font loading and shaping, the hardest part without dependencies.
- **Language features**: SwiftUI leans on result builders (a DSL for view trees), property wrappers for state and protocols with associated types. Myla's closures, pipelines and value semantics cover some of it; a builder syntax probably needs user macros or a dedicated feature.
- **An event loop**: overlaps with concurrency ([[MYLA-61]]).
- File descriptors, sockets and `mmap` in the standard library.

## Done when

- [ ] A design sketch (target platform, rendering approach, the view/state model in Myla syntax) on a wiki page
- [ ] A first prototype target chosen
