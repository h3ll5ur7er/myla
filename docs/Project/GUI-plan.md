# GUI plan

A brainstorm of 18 November 2026 for the next phase of development: a cross-platform, declarative GUI system that looks and feels close to SwiftUI ([[MYLA-63]]). Nothing here is decided. The pages below hold the findings, the answers to the five questions the owner asked, and proposals to choose from; no tasks were created and no existing file was changed.

[SUBPAGES]

| Page | Answers |
| --- | --- |
| [[Project/GUI-plan/Prerequisites]] | Which planned tasks must be finished before starting, which before a given platform, and which don't matter |
| [[Project/GUI-plan/Gaps]] | The language, standard library, runtime and platform gaps that no task covers yet |
| [[Project/GUI-plan/Architecture]] | The layers from the platform's window up to the app, the frame pipeline, the state model, the platforms, the phases |
| [[Project/GUI-plan/Syntax-without-grammar-change]] | What a SwiftUI-like API looks like in today's Myla, with a program that runs |
| [[Project/GUI-plan/Syntax-with-grammar-change]] | Grammar changes in three tiers, from small general features to a `view` declaration |
| [[Project/GUI-plan/Data-bindings]] | How a control reads and writes state: bindings as values, conversions, what a message per field costs |
| [[Project/GUI-plan/Testing-and-automation]] | Five levels from `#test` on a model to the built program driven over a socket; pictures, replay, generated tests |
| [[Project/GUI-plan/Styling]] | Themes as data, inherited attributes, control styles as functions, named styles, the platform look |
| [[Project/GUI-plan/Concurrency]] | The UI task and its inbox, jobs, actors as services, what crosses between tasks, cancelling, and the task group that is missing |

[TOC]

## The short answers

**1. Planned tasks to finish first** ([[Project/GUI-plan/Prerequisites]]). Before any GUI code: round 7's review queue merged (the native memory and place-write bugs are in exactly the code shapes a view tree uses), the design round on what std is and how code is chosen per target ([[MYLA-245]]), leading-dot continuation ([[MYLA-589]]) and private fields ([[MYLA-433]]). Before the first real window: one Linux platform layer ([[MYLA-758]]) and the poller in Myla's terms ([[MYLA-265]], [[MYLA-885]]). The C FFI ([[MYLA-166]]), macOS ([[MYLA-164]]) and wasm exports ([[MYLA-241]]) gate single platforms, not the start.

**2. Gaps no task covers** ([[Project/GUI-plan/Gaps]]). The three that shape the design:
- **No type-erased storage with typed recovery** (no trait objects, no `Any`, no shared cell): SwiftUI's `@State`, state that belongs to a view and survives its parent's rebuild, can't be written in Myla today. A model with messages can.
- **No way to hand a window's pixels to the system**: Unix-domain sockets, shared memory, descriptor passing, Windows' `user32`/`gdi32` with a callback, a canvas import on wasm.
- **No text rendering**: font parsing, glyph rasterising, line breaking, `std.unicode`.

**3. Architecture** ([[Project/GUI-plan/Architecture]]). Six layers: a per-target window layer in `std.platform`, a `window` module (events, a surface), a software renderer that executes a display list, text, the declarative core (view values, a retained element tree, layout, events, state), and the widgets. Myla draws every pixel itself, so a view looks the same on every target and can be tested as a picture without a display. The display list is the seam where `myla run` hands over to compiled code: interpreted pixel loops are about 1,200 times slower than native ones (measured below).

**4. Syntax without a grammar change** ([[Project/GUI-plan/Syntax-without-grammar-change]]). Views are values built by functions, children are list literals, modifiers are methods; state is a model struct with an `update` for messages. It type-checks and runs today, interpreted and native:

```myla fragment
fun body(self, ui: Ui<Msg>) -> View {
    return vstack([
        text(f"{self.name}: {self.count}")
            .font(Font.Title),
        hstack([
            button("-", ui.send(Msg.Decrement)),
            button("+", ui.send(Msg.Increment)),
        ])
            .padding(8),
        text_field(self.name, ui.send_text((s) => Msg.Rename(s))),
        if self.count > 9 { text("big") } else { empty() },
    ])
}
```

**5. Syntax with a grammar change** ([[Project/GUI-plan/Syntax-with-grammar-change]]). Three tiers, each usable without the next: (1) small general features (named arguments, `if` and `for` as list elements, `.title` for an expected enum, leading-dot continuation); (2) trailing blocks that collect views; (3) a `view` declaration with `state`:

```myla fragment
view Counter(title: str) {
    state count = 0

    body {
        VStack(spacing: 8) {
            Text(f"{title}: {count}")
                .font(.title)
            HStack {
                Button("-") { count -= 1 }
                Button("+") { count += 1 }
            }
            if count > 9 {
                Text("big")
            }
        }
        .padding(16)
    }
}
```

## What was measured and tried

Done on 2026-11-18 at `dd57b05`, on a 4-CPU Xeon at 2.1 GHz, with the tools built by `scripts/bootstrap.sh`:

| Probe | Result |
| --- | --- |
| A non-generic `View` whose actions are erased by closures, a model with messages, a text field, a conditional child | Checks; prints the same under `myla run` and natively (the program on [[Project/GUI-plan/Syntax-without-grammar-change]]) |
| A generic `View<M>` (the message type in the view's type) | `text("x").font(f)` fails: `cannot infer type parameter(s) M for 'text'`. The expected type doesn't reach a call through a method chain, so leaves would be written `text<Msg>("x")` |
| A leading-dot modifier chain | Works inside `[ ]` and `( )`, where line breaks don't end statements, so in every child list. Fails only on the outermost view ([[MYLA-589]]) |
| An enum variant as a function value (`ui.send_text(Msg.Rename)`) | `variant 'Msg.Rename' takes 1 argument(s); call it like 'Msg.Rename(...)'`: a lambda is needed |
| `xs + ys` on lists | `operator '+' requires numeric or string operands`; `xs.concat(ys)` works |
| A function named `Text` | Accepted: capitalised function names are only a convention |
| `f(1) { … }`, `f(1, y: 3)`, `g(.Title)`, `[1, if c { 2 }]` | Each is a parse error today, so none of the proposed forms changes the meaning of a valid program |
| Bindings (`Binding<T>` with a two-way `map`), a view found by its id and edited, a theme decoded with `#derive(Toml)`, a button style as a function of its state, a message log encoded to JSON and replayed | Checks; prints the same under `myla run` and natively (at `4ad9493`) |
| A UI task over an inbox channel, actions that post messages, jobs run by `task.workers`, an actor reporting progress through a sender while a scripted user keeps pressing a button (190 lines) | Checks and runs under `myla run` and natively: the presses land between the progress reports ([[Project/GUI-plan/Concurrency]], at `f78f57c`) |
| Filling a 1920×1080 `[uint32]` in a plain Myla loop, native | 4 ms a frame (2 ns a pixel) |
| Source-over blending the same area, native | 10 to 15 ms a frame |
| The same two loops under `myla run` (at 192×108, scaled by 100) | 4.9 s and 24 s a frame: about 1,200 and 1,600 to 2,400 times slower |

## Decisions the owner would have to take

In the order they block work. Each has a recommendation on the page that discusses it.

| # | Decision | Recommendation |
| --- | --- | --- |
| 1 | **Where the GUI lives**: std, an official package, or both ([[MYLA-245]]; the roadmap's "left out" says package, the owner leaned toward std) | Both: the window layer, the renderer and text in std (they need primitives and compiled speed under `myla run`), the declarative framework as a package of pure Myla |
| 2 | **Who draws**: Myla's own renderer everywhere, or each system's drawing and text | Myla's own: the same pixels on every target, golden-image tests, no FFI for Linux. Native text and GPU drawing can replace the renderer behind the display list later |
| 3 | **The state model**: a model with messages, shared state cells, or both | Both, in that order: the model with messages first (no language change, testable with `#test`), then cells for a view's own state once type-erased storage exists |
| 4 | **Type-erased storage**: a cell primitive in std, an `Any` type, or trait objects | A cell primitive first (small, std-only), trait objects as a language feature of their own later |
| 5 | **Grammar**: none, tier 1, tier 2 or tier 3 | Tier 1 before the framework's API is published (named arguments change every signature); tiers 2 and 3 after the framework has been used without them |
| 6 | **Names**: `vstack` and `text` (Myla's convention for functions) or `VStack` and `Text` (SwiftUI's look) | Lower-case for functions; capitalised only where a `view` declaration makes them types (tier 3) |
| 7 | **The first targets** | A headless target and the terminal first, then X11 on Linux, Windows, the browser, then Wayland and macOS |

## Proposed phases

Each phase ends with something that runs and is tested; none needs the one after it.

1. **Decisions and prerequisites**: the table above, and the tasks of [[Project/GUI-plan/Prerequisites]].
2. **The declarative core without pixels**: view values, state, the element tree, layout, events and focus, against a headless target (a tree and a grid of character cells) and the terminal through `std.term`. This proves the API on every target and under the interpreter with no platform work.
3. **Pixels without a window**: the software renderer, fonts and text, PNG output; golden-image tests on every target.
4. **The first window**: X11 on Linux, both architectures.
5. **Windows**, then **the browser**.
6. **Later**: Wayland, macOS, accessibility, input methods, animation, a GPU renderer.
