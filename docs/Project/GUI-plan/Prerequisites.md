# Prerequisites

Which of the tasks open on 18 November 2026 (at `dd57b05`: 110 of 567 not done) the GUI work depends on. The gaps that no task covers are on [[Project/GUI-plan/Gaps]].

Brought up to date on 27 November 2026 (at `28fc64a`: 157 of 618 not done). Since the first version, [[MYLA-758]] and [[MYLA-861]] were built and wait in review, round 7's proposals were accepted, and D313's modules landed ([[MYLA-956]] to [[MYLA-971]], all in review): std.image, std.png, std.draw and std.font are what phase 3 of [[Project/GUI-plan]] builds on. The image lanes also filed the compiler's costs they measured, which bear on the renderer's speed (below).

[TOC]

## Before any GUI code

| Task | State | Why the GUI needs it |
| --- | --- | --- |
| Round 7's review queue: [[MYLA-543]], [[MYLA-791]], [[MYLA-809]], [[MYLA-811]], [[MYLA-790]], [[MYLA-792]] | review; the fixes are in master, and the owner accepted wave A's proposals on 2026-11-18 (D263 to D278) | A view tree is nested lists of structs holding closures, rebuilt and changed in place on every event, partly in async code. These tasks fix a value freed by a later operand, a mutating call on a place that writes a copy when the call awaits, and `g[^at(1)].push(9)` writing `g[0]`. A GUI built before they are closed would find them again, in a setting where they are far harder to reduce |
| [[MYLA-612]], [[MYLA-585]], [[MYLA-587]] | review | Operators between different types, float methods, and `std.vector`/`std.matrix`: points, sizes, rectangles, insets and affine transforms are written with them |
| [[MYLA-245]] | backlog | The design round on what std is, official packages and **code chosen per target**. It decides where every GUI file goes (decision 1 of [[Project/GUI-plan]]), and the window layer is the largest per-target code after `std.platform` itself |
| [[MYLA-589]] | backlog | A line that starts with `.method` continues the expression. Modifier chains are the most common line in a SwiftUI program. They already work inside `[ ]` and `( )`, so in every child list; the outermost view of a `body` needs parentheses until this is built. Its match-arm rule also has to agree with tier 1's `.title` ([[Project/GUI-plan/Syntax-with-grammar-change]]) |
| [[MYLA-433]] | backlog | Private fields and methods of a `pub` type. A framework's `View`, `State` and `Window` hold identities and handles a program must not write; today every field is public API. Deciding this after publishing the framework's types means migrating them |

## Before the first window

| Task | State | Why |
| --- | --- | --- |
| [[MYLA-758]] | review (built: D305, D306) | One Linux platform layer for x86-64 and aarch64. Without it the X11 (and later Wayland) code in the platform module would be written twice; since 2026-11-19 `platform.my` serves both architectures over the generic system calls, with the numbers in `std.linux_calls`, and `platform_aarch64.my` is gone |
| [[MYLA-265]], [[MYLA-885]] | backlog | The platform interface and the poller in Myla's terms. A window is a new source of events for the poller on every target: a socket on Linux, a message queue on Windows, the host on wasm. The interface should name such sources before a fourth family of platform functions is added to four platform modules |
| [[MYLA-181]] | backlog | One builtin table for the checker, the interpreter and the lowering. The window layer adds a dozen or more primitives, each of which is written in three places today |
| [[MYLA-296]], [[MYLA-531]], [[MYLA-755]] | backlog, backlog, review | The timer lock taken at every loop top while a timer is armed, the poller taking four events a wait, and how often a busy worker looks at the poller. An animating window keeps a timer armed all the time and gets input in bursts |
| [[MYLA-317]] | backlog | The interpreter's speed. Under `myla run` the framework's rebuild, diff and layout are interpreted on every event; only the pixels can be handed to compiled code ([[Project/GUI-plan/Architecture#under-the-interpreter]]) |
| [[MYLA-368]], [[MYLA-257]] | backlog | x86-64 code quality in hot loops and register allocation on intervals. The renderer's inner loops are such loops: a plain fill takes 2 ns a pixel today, several times a `memset` |
| [[MYLA-949]], [[MYLA-950]], [[MYLA-951]], [[MYLA-947]] | todo | Filed by the image lanes (2026-11-24 and 25): `list.filled` pushes one element at a time, so allocating a pixel buffer costs a pass over it; native `float32` arithmetic goes through `float64` and back; a slice copies element by element; small `var self` methods of another module's struct cost 1.7 to 2.6 times the loop by hand. std.draw's coordinates are `float32`, and it allocates its rasteriser's rows and every mask with `list.filled`, so each of them bears on a frame's cost |
| [[MYLA-314]] (Unicode, #10 of [[Project/Standard-library-roadmap]]; text layout, #9) | todo | Grapheme clusters for the text cursor, line-break opportunities, case mapping beyond ASCII. std.font's layout ([[MYLA-969]]) breaks lines at spaces and tabs only, and #10 still has no task of its own |

## Before a given platform

| Platform | Tasks | Why |
| --- | --- | --- |
| The terminal | [[MYLA-760]] | A key at a time on Windows' console: Enter is a CR there |
| Windows | [[MYLA-165]] finished; [[MYLA-166]] or a std-only shortcut; [[MYLA-776]]; [[MYLA-861]] (built, in review) | Windows are `user32` and `gdi32`, which aren't in `windows_dlls` ([[selfhost/codegen.my]], D228), and a window procedure is a callback from the system into the program. The console control handler shows the shortcut (a routine of the runtime's, D230, D277); the general answer is the FFI. A callback runs under the system's frames, so unwind tables matter more than for a console program. Each worker that allocated committed 16 MiB; since D298 the heap is committed in steps of 256 KiB, and what is left is [[MYLA-886]] (the polling worker still allocates while the program waits) |
| The browser | [[MYLA-241]] (the wasm part: exports), [[MYLA-505]] | A page can't block. Today a wasm program's read blocks its host ([[Language/Targets]]); a GUI program has to return to the browser and be called again for each event and frame, which needs exported entry points and a scheduler that can be re-entered |
| macOS | [[MYLA-164]] with [[MYLA-262]] and [[MYLA-269]]; [[MYLA-166]] | AppKit is reached through the Objective-C runtime, on the main thread only |
| A GPU renderer, native text, system widgets | [[MYLA-166]] | As [[MYLA-63]] says: OpenGL and Vulkan are C libraries |

## Not needed

- [[MYLA-434]] (async methods in traits): the framework's traits are synchronous; async work goes through effects ([[Project/GUI-plan/Architecture#state-and-effects]]).
- [[MYLA-227]] (generic bodies checked against their bounds): it would give better errors in the framework's generic code, nothing more.
- [[MYLA-624]] (a deep type refused as polymorphic recursion): SwiftUI's own design, where every modifier wraps the view's type in another generic, would run into it. The proposal avoids it with one `View` type.
- [[MYLA-802]], [[MYLA-274]], [[MYLA-260]], [[MYLA-259]], the website and HTTP tasks.

## What this changes in existing tasks

Not edited, beyond a link to this plan in [[MYLA-63]] (the owner asked for no changes yet); to carry over when tasks are written:

- [[MYLA-63]] says the GUI is on hold until the toolchains, the IR, concurrency and a project tool fit. All four are built. Its first "done when" box, a design sketch on a wiki page, is this page and its siblings; the second, a first prototype target, is decision 7.
- [[MYLA-63]] and [[MYLA-166]] tie the GUI to the C FFI. That holds for GPU drawing and for macOS. A software renderer on Linux needs no FFI at all (std.draw and std.font are pure Myla with no primitive, D313), and Windows needs two more system DLLs and one callback, which the Windows port already has in miniature.
- The roadmap's ideas table calls [[MYLA-63]] "on hold until everything else fits; GPU APIs would need a C FFI".
- [[MYLA-63]]'s "What it would need first" lists a software rasteriser and font loading: std.draw and std.font ([[MYLA-968]], [[MYLA-969]]) are both, shaping aside.
