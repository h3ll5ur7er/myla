# Gaps

What a SwiftUI-like GUI needs that Myla, its standard library, its runtime and its platform layers don't have on 18 November 2026, and that no open task covers. Tasks that exist are on [[Project/GUI-plan/Prerequisites]]. Each gap says whether it blocks the start, blocks a phase, or only costs comfort.

Brought up to date on 27 November 2026 (at `28fc64a`): the language, runtime and platform gaps stand as they were, with notes where D313's modules bear on them; in the standard library, images, a renderer's drawing and fonts exist now (D313, [[MYLA-956]]), and the table below says what of each a GUI still lacks.

[TOC]

## Language

### L1 Type-erased storage

Blocks a view's own state.

SwiftUI keeps a view's `@State` outside the view, in storage the framework owns, keyed by the view's identity. The framework doesn't know the state's type; the view gets it back typed. Myla has no way to write that:

- no trait objects ([[Language/Methods-and-traits]]), so no `[any Storage]`;
- no `Any` and no downcast;
- no shared mutable cell: closures capture copies and can't change them (D93), and there are no global variables.

Closures do give one-way erasure: a struct of closures that captured a typed value is an object whose type doesn't show the value's. That is enough for a model with messages (the program on [[Project/GUI-plan/Syntax-without-grammar-change]] does it). It isn't enough for a view's own state, because the next rebuild brings a new typed `body` that has to be joined with the old erased state, and nothing can open the erasure again.

Three ways to close it, smallest first:

| Option | What it is | Cost |
| --- | --- | --- |
| A cell primitive | A std-only handle, as `task.Notifier` is: `Cell<T>` with `get()`, `set(v)`, storage in the runtime, values copied in and out under std.rt's lock | A handful of primitives and a small std module. It is a second kind of shared state beside actors, which D93 chose not to have for closures |
| `Any` | A built-in type holding any value with its type's identity; `any.get<T>()` gives an `Option<T>` | A new built-in type through the checker, the interpreter and every backend's ownership routines (step 11 of the feature checklist) |
| Trait objects | `any View`, `[any Shape]`: dynamic dispatch through a table | The largest: a language feature of its own (it is on the roadmap's "proposed after 1.0" list). It would also give custom layouts, custom shapes and mixed iterator lists |

The recommendation is the cell primitive for the GUI, and trait objects decided on their own merits.

### L2 Closures can't change anything

Shapes the action syntax.

`Button("+") { count += 1 }` is SwiftUI's most typical line. In Myla a lambda can't assign what it captures (D93), a lambda's parameters are immutable, and there are no `var` parameters. So an action can't be "a closure that changes the state". What works today: the action is a value (a message) and one `update(var self, msg)` method changes the state. What would make the SwiftUI form possible:

- by-reference capture (`ref`, planned since D15 and D48), or
- `var` parameters on lambdas and function types (`(var m: Counter) => { m.count += 1 }`, copy in and copy out as a `var self` method on a built-in type is, D144), or
- a cell (L1), whose `set` isn't a change of a captured variable, or
- a `view` declaration whose compiler rewrites the block (tier 3 of [[Project/GUI-plan/Syntax-with-grammar-change]]).

### L3 Inference through a method chain

Decides the tree's type.

`text("x").font(f)` with `fun text<M>(s: str) -> View<M>` fails with `cannot infer type parameter(s) M for 'text'`: the expected type reaches a call only directly (as an argument, a list element, an annotated `let`), not through `.font(…)`. A view type that carries the message type (`View<Msg>`, as Elm's `Html msg` and iced's `Element<Message>` do) would therefore need `text<Msg>("x")` on every leaf that has a modifier. The proposals use one non-generic `View` and erase the action instead. Inference that leaves a type variable open until a later use would lift this; it is a deep change to the checker and isn't proposed.

### L4 No trait default bodies

Costs comfort.

A program's own view type can't inherit the modifiers. `MyRow { … }.padding(8)` would need every modifier written again in an impl for `MyRow`. The proposals make a custom view a function or a method that returns the one `View` type, so the modifiers are `View`'s. Pipe-able free functions (`v |> padding(8)`) work for any type with a bound, and `|>` at a line's end continues the line.

### L5 No named arguments

Costs the SwiftUI look.

`VStack(alignment: .leading, spacing: 8)` reads well because of its labels. Myla's calls are positional, defaults can only be left out from the end, and a struct literal needs every field. A view with five optional settings is therefore either a chain of modifier methods (which works today and is the proposal) or a call with five positions. Named arguments are tier 1 of [[Project/GUI-plan/Syntax-with-grammar-change]].

### L6 Smaller ones

| Gap | Effect | Way around it today |
| --- | --- | --- |
| An `if` used as a value needs an `else`; a list literal has no `for` | A conditional or repeated child | `if c { v } else { empty() }`, `when(c, v)`, `for_each(xs, (x) => row(x))`, `xs.map<View>(f)` with `a.concat(b)` |
| An enum variant isn't a function value | `ui.send_text(Msg.Rename)` | `(s) => Msg.Rename(s)` |
| No `+` on lists | Joining child lists | `a.concat(b)` |
| No implicit member (`.title`) | `Font.Title`, `Color.Red`, `Alignment.Leading` spelled out | Nothing; tier 1 |
| No struct field defaults, no `P { ..base }` | Style and configuration structs with many fields | Builder methods that return a changed copy (`style().fg(c).bold()`, as `std.term` does) |
| No way to put a file's bytes into a program | A bundled default font, icons, images | Read them at run time; or a generated `.my` file with a byte list, which is slow to check and large. An `embed` constant or attribute would be a small feature of its own. std.draw's built-in bitmap font (ASCII, 6 by 10, D313) is kept in `draw.my` itself, so text with no file works, though not in a TrueType face |
| Doc comments only on the website | A framework's API in the editor | The comment above a declaration is read by the API reference's generator ([[MYLA-632]]), not yet by the language server's hover |
| A captured value is copied into each closure, and values cross tasks as deep copies (D93) | A large model sent to a background task is copied | Send only what the task needs |

## Runtime

### R1 Something that owns a thread

Blocks Windows and macOS.

Tasks run on work-stealing workers; a task can resume on any of them. Windows delivers a window's messages to the thread that created it, and AppKit works on the main thread only. X11 and Wayland sockets don't care, and wasm has one thread. Two ways:

- **A platform thread** (recommended): the window layer on Windows starts one thread of its own that creates the windows and runs the message loop, and hands events to the poller as packets on the completion port, as the console control handler already does (D244). The scheduler doesn't change.
- **A pinned task**: a way to say that a task or an actor runs on the main thread only (Swift's `@MainActor`). More general, and a change to the executor.

### R2 A host-driven loop on wasm

Blocks the browser.

In a page the program must return to the browser between events. The scheduler would need an entry point the host calls ("run until every task waits, then return"), and the window layer's event wait would be "return to the host" instead of a blocking `poll_oneoff`. The alternatives: run the program in a Web Worker and block there on a shared buffer (needs cross-origin isolation headers, which GitHub Pages doesn't send), or the browsers' promise integration for wasm (not in every browser).

### R3 Bulk memory operations

`__copy_bytes` exists; a fill of 32-bit words and a row blend don't. A plain loop fills at 2 ns a pixel. Either the hot-loop tasks ([[MYLA-368]], [[MYLA-257]]) bring that near a `memset`, or the renderer gets two or three primitives, std-only. std.draw is written without any primitive and composites about 100 million translucent pixels a second natively; the image lanes filed a fill of a new list ([[MYLA-949]]: `list.filled` pushes element by element) and slices copied as a block ([[MYLA-951]]), which cover part of this gap.

### R4 Compiled std code under the interpreter

The interpreter runs its primitives through the std compiled into the `myla` binary. The rest of std it interprets, std.draw and std.font included (a 3×3 blur runs at about 12,000 pixels a second interpreted, [[Project/Standard-library-roadmap/Images-vision-and-fonts#what-was-measured]]). The renderer would use the compiled std on purpose: `myla run` interprets the framework and calls the compiled renderer through one primitive that takes a display list ([[Project/GUI-plan/Architecture#under-the-interpreter]]). Nothing new in kind, but it makes the renderer part of every `myla` binary.

## Platform

| Gap | Needed by | Notes |
| --- | --- | --- |
| Unix-domain stream sockets | X11, Wayland | `std.net` has TCP and UDP only. X11 also runs over TCP, but no desktop listens there |
| Shared memory: an anonymous file and a mapping of it | Wayland (required), X11 (optional, for speed) | `memfd_create` and `mmap` of a descriptor |
| Passing a descriptor over a socket (`SCM_RIGHTS`) | Wayland (required: buffers and the keymap arrive as descriptors) | `sendmsg`/`recvmsg` with ancillary data |
| `user32.dll`, `gdi32.dll` and a window procedure | Windows | The import table is fixed in the compiler (D228); a callback needs a routine in the runtime or the FFI |
| A canvas and input events as imports | The browser | A second host interface beside WASI: a wasm module that imports `myla_gui` isn't a WASI program any more |
| The X authority file, the display's name | X11 | Plain file reading and parsing; no gap, only work |
| A keymap | Every platform | X11 sends key symbols on request (simple). Wayland sends an XKB keymap as text, which needs a parser of its own. Windows sends characters |
| The clipboard, the cursor's shape, the window's title and icon, drag and drop | Every platform | A protocol each: X11 selections, Wayland's data device, Windows' clipboard API |
| Display scale | Every platform | X resources or XSETTINGS, Wayland's scale events, Windows' per-monitor DPI |
| Input methods (composing text, dead keys beyond the keymap) | Text fields in many languages | Windows gives most of it with `WM_CHAR`; X11 (XIM) and Wayland (text-input) are large. Not in the first phases |
| Accessibility | Screen readers | AT-SPI over D-Bus on Linux, UI Automation on Windows. Large; the architecture keeps a semantic tree so it can be added |

## Standard library

| Module | What | Size | Notes |
| --- | --- | --- | --- |
| Geometry | `Point`, `Size`, `Rect`, `Insets`, an affine transform | Small | std.draw takes points as std.vector32's `Vec2` and transforms as std.matrix32's `Mat3`, and std.image has an integer pixel `Rect`. Missing: a `Size`, a `Rect` and `Insets` in points (`float32`) for layout |
| Colour | `Color` with sRGB and linear conversions, named colours, premultiplied pixels | Small | std.image's `Color` exists (8-bit sRGB, straight alpha, `parse_color`, `lerp`), with premultiplied images and std.imgproc's `to_linear`. Missing: named colours, and linear light for one colour. `std.term.Color` is the terminal's and stays |
| Images | A pixel buffer type; a PNG decoder and encoder | Medium | Done: std.image's `Image<S>` and std.png ([[MYLA-959]], [[MYLA-961]]), with JPEG, GIF, TIFF, BMP, PNM and QOI, and std.imageio over them |
| A renderer | Filled and stroked paths with anti-aliasing, rounded rectangles, gradients, images, clipping, transforms, a display list | Large | std.draw ([[MYLA-968]]) has all of it but the display list: exact-area coverage, strokes with joins, caps and dashes, linear and radial gradients, patterns, images drawn and scaled, a transform and clip stack, pure Myla. Missing for a GUI: the display list and its damage, clip paths (the clip is a rectangle of pixels), blend modes beyond source-over. Blurs for shadows are std.imgproc's |
| Fonts | TrueType and OpenType parsing (`cmap`, `glyf`, `hmtx`, `kern`, later `CFF` and `GPOS`), outlines to coverage, a glyph cache | Large | std.font ([[MYLA-969]]) has TrueType and collections, `cmap` formats 4 and 12, composite glyphs, `kern`, unhinted masks at quarter pixels within 5 levels of FreeType, and a glyph cache. Missing: `CFF` (`.otf`) and `GPOS`, and finding the system's fonts without fontconfig (the known directories); a bundled TrueType font still needs L6's embedding |
| Text layout | Line breaking, alignment, truncation, measuring; later bidirectional text and shaping for complex scripts | Large | std.font's `layout` and `measure` break lines at spaces, tabs and `\n` within a width, align left, centre or right, and measure, enough for Latin, Greek and Cyrillic. Missing: truncation, Unicode line breaking, a placed glyph's character (for a cursor and selection), bidirectional text and shaping, which D313 leaves out. `std.text.wrap` and `std.term.width` do it for cells |
| `std.unicode` | Grapheme clusters, line-break classes, case mapping | Medium | #10 of [[Project/Standard-library-roadmap]], still without a task; [[selfhost/unicode.my]] has the identifier tables only |
| A window module | Windows, events, a surface, the clipboard | Medium, per target | Over the platform gaps above |
| Animation | Curves, springs, a frame clock | Small | `std.time` and `std.task` carry it |

## What the foundation already has

So that the list above isn't read as "everything is missing":

- `std.task`: the event loop is an async task; timers, channels, notifiers, structured children for background work.
- `std.term`: raw mode, keys, colours, cell widths. A terminal target for the framework needs nothing else.
- `std.vector`, `std.matrix`, float methods, operators between types (in review).
- `std.compress`, `std.checksum`, `std.bytes`, `std.fs`: image and font files.
- Since D313: `std.image` and its codecs, `std.draw` (the drawing a renderer needs, and a bitmap font) and `std.font` (TrueType glyphs, a glyph cache and a simple layout), compared with Pillow and FreeType in the burn suites.
- `std.json`, `std.toml` with `#derive`: themes, settings, and state that can be saved.
- `std.test` and `#test`: a view's body is a function of its model, so `#test(model)[expected]` works on it.
- Floats that give the same bits on every target (`std.math` is Myla code): layout computes the same on every target.
- The platform pattern: `std.net`, `std.term` and `std.signal` each sit on a few `std.platform` functions per target and never see the system. A window module follows it.
