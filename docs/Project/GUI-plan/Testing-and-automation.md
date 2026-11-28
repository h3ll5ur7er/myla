# Testing and automation

How GUI programs are tested from a single function up to the built program driven from outside. Part of [[Project/GUI-plan]]; a follow-up to the owner's question of 18 November 2026. [[Project/GUI-plan/Architecture#testing]] has the short version.

[TOC]

## What Myla gives a GUI test that other toolkits fight for

- **Determinism.** The framework draws its own pixels with its own fonts and computes layout with `std.math`, whose results are the same bits on every target ([[Language/Targets]]). A picture is the same bytes on x86-64, aarch64, wasm32 and Windows.
- **No display needed.** The headless target is a window in memory.
- **Time under control.** The interpreter already has a virtual clock (`MYLA_TIME=virtual`: time moves only when every task sleeps) and both runners a seeded scheduler (`MYLA_SCHED=seed:N`); with a clock the test advances, a test of an animation or a debounce doesn't sleep.
- **State as values.** A model can be compared, printed, saved; a message too.
- **Two runners that must agree.** The burn suites run every program interpreted and natively and compare. GUI programs join them unchanged.

## The levels

| Level | Tests | Runs | Speed |
| --- | --- | --- | --- |
| 1. Model | `update`: a model and a message give a model | `#test` cases, no framework | Microseconds |
| 2. View | `body`: a model gives a tree | In process, headless | Microseconds |
| 3. Interaction | A sequence of user actions against the running core: focus, keys, pointer, effects, time | In process, headless, virtual time | Milliseconds |
| 4. Picture | The pixels of a view or a window | In process, headless renderer | Tens of milliseconds |
| 5. End to end | The built program, a real or headless window, driven from another process | `myla test` in a project, `tests/` | Hundreds of milliseconds |

### 1. Model

Nothing new: `update` is a method on a value, so a test function builds a model, sends it messages and compares (the model has `#derive(Eq)`).

```myla fragment
#test
fun incrementing_counts() {
    var c = Counter { name: "a", count: 1 }
    c.update(Msg.Increment)
    expect(c == Counter { name: "a", count: 2 })
}
```

### 2 and 3. View and interaction

A driver over the headless target. It finds views the way a user does and acts on them:

```myla fragment
#test
async fun renaming_shows_the_new_name() {
    var app = ui.test(Counter { name: "apples", count: 0 })
    app.press(by.label("+"))
    app.press(by.label("+"))
    app.type_into(by.id("name"), "pears")
    expect(app.exists(by.text("pears: 2")))
    expect_eq(app.tree(), "VStack\n  Text pears: 2\n  …")
    await app.advance(300)                       // virtual milliseconds
    expect(!app.exists(by.id("saving")))
}
```

- **Queries** go through the semantic tree, not the view tree: `by.id("save")` (the program's `.id("save")`), `by.label("Save")`, `by.text(…)`, `by.role(Role.Button)`, and `within(by.id("row-3"), by.role(Role.Toggle))`. A query that matches none or several fails with the tree printed.
- **Actions** are the user's: `press`, `type_into`, `key(Key.Tab)`, `scroll`, `drag`, `hover`, `focus`. They go through hit testing and focus as real events do: a button behind a sheet can't be pressed.
- **Waiting** is explicit and virtual: `app.advance(ms)`, `app.settle()` (run until no task is ready, no frame is due and no timer is armed below a limit). No polling, no sleeps.
- **Effects** are swapped at the edge: the model takes its clock, its HTTP client and its files as values, so a test passes fakes. This is a convention the framework's examples should follow, not a feature.
- The probe on [[Project/GUI-plan/Data-bindings]] did the first step of this by hand: find a field by id, set its text, read the tree.

### 4. Pictures

```myla fragment
#test
fun the_settings_sheet_looks_right() {
    var app = ui.test(Settings { … }).size(480, 320).scale(2.0).theme(ui.dark())
    app.expect_picture("settings-dark")          // tests/pictures/settings-dark.png
}
```

- A missing or different picture fails and writes the new one beside a difference picture; `MYLA_PIN_PICTURES=1` accepts, as `MYLA_PIN_DIAGNOSTICS=1` does for pinned diagnostics.
- Exact comparison by default, because the renderer is deterministic; a tolerance exists for pictures that include a system's text or a GPU renderer later. The codec suites work this way already: expected pixels made once with Pillow and committed under `tests/burn/data/`, compared exactly on every target (D313).
- A single view can be pictured without an app: `ui.picture(card(item), 200, 80)`.

### 5. End to end

The built program, as a user starts it. Two parts:

**An automation server inside every program**, off by default. Started with `MYLA_UI_AUTOMATION=127.0.0.1:0` (or a Unix socket), the framework serves a small protocol, JSON lines over the socket, from the UI task:

| Request | Answer |
| --- | --- |
| `tree` | The semantic tree: roles, labels, ids, values, states, rectangles |
| `find` with a query | The matching nodes |
| `press`, `type`, `key`, `scroll`, `drag` with a node or a point | Done, after the frame that followed |
| `screenshot` | A PNG of the window |
| `settle`, `advance` | As in process |
| `windows`, `resize`, `close` | |

It is WebDriver's idea at a hundredth of the size. `std.net` and `std.json` carry it; the model and the messages aren't exposed, only what a user could see and do.

**A client in the test library** that starts the program and speaks the protocol with the same calls as the in-process driver:

```myla fragment
#test
async fun the_built_app_saves_a_file() {
    let dir = test.temp_dir()
    var app = await ui.launch(test.program(), ["--data", dir]).expect("the app starts")
    await app.press(by.label("New"))
    await app.type_into(by.id("title"), "Shopping")
    await app.key(Key.Ctrl('s'))
    expect(fs.exists(path.join(dir, "Shopping.json")))
    await app.quit()
}
```

- `test.program()` already names a project's built program for the files in `tests/`.
- The same test runs against the headless window (`MYLA_UI_HEADLESS=1`, the default under `myla test`) and against a real one on a desktop, where it also covers the platform layer.
- Because the protocol is JSON over a socket, a script in any language, an AI agent or a screen recorder can drive a Myla program. That is worth stating as a goal: programs that can be operated by tools.

## Record and replay

- **Messages are values.** With `#derive(Json)` on the message type, a session is a list. The probe encoded `[Msg.SetAge(41), Msg.SetName("Grace")]` as `[{"SetAge":41},{"SetName":"Grace"}]`, decoded it and replayed it onto a fresh model to the same state. A bug report can be "this model, these messages"; a regression test is the same file.
- **Events are values too**, one level lower: the window module's `Event`s with their times. Recording them works for every state model, and replaying them through the headless window with the virtual clock reproduces the pictures.
- A recorder that turns a session into a level 3 test (queries instead of coordinates) is a tool for later.

## Generated tests

- **Random messages** against `update` with an invariant (`model.total() >= 0`), as the review rounds' generators do for the compiler.
- **Random events** against the headless app (a "monkey"): no runtime error, no layout with negative sizes, the tree always has exactly one focus. The seed reproduces a failure.
- **Every view at every size**: a view pictured at a list of widths, scales and themes, checked for clipped or overlapping text by the semantic tree's rectangles, not by eye.

## Accessibility and automation are one tree

The semantic tree (role, label, value, state, actions, rectangle of each element) is built once and has three readers: tests, the automation protocol, and later the system's accessibility interface (AT-SPI, UI Automation). A control without a label fails a test before it fails a screen reader's user. A lint, `app.audit()`, reports unlabelled controls, contrast below a threshold and targets smaller than a minimum.

## What it needs

| Need | From |
| --- | --- |
| A headless window target and the semantic tree | The core, phase 2 of [[Project/GUI-plan]] |
| A clock a test advances, in both runners | The interpreter's virtual clock is set by an environment variable for `myla run` and native code has none ([[Language/Concurrency]]); the framework's frame clock can be its own, injected into the UI task, which needs nothing from the runtime |
| PNG encoding and decoding | std.png ([[MYLA-961]], D313) |
| `#test` on an `async fun` | Exists |
| A `Format` or `Eq` for trees, to compare and print them | The framework's |
| A bundled font | std.draw's built-in bitmap font needs no file. For TrueType text, a test can vendor its font as std's suites do (`tests/burn/data/images/fonts/MylaTestSans.ttf`, a subset of Liberation Sans); a program's own default font needs embedding ([[Project/GUI-plan/Gaps#l6-smaller-ones]]), without which its pictures depend on the machine's fonts |
