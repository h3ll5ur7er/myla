# Syntax without grammar change

What a SwiftUI-like API looks like in the Myla of 18 November 2026: no new syntax, no new primitive for the part that is shown running. Part of [[Project/GUI-plan]]; the forms that need new syntax are on [[Project/GUI-plan/Syntax-with-grammar-change]].

[TOC]

## SwiftUI's forms and Myla's

| SwiftUI | Myla today | Note |
| --- | --- | --- |
| `struct Counter: View { var body: some View { … } }` | `impl Model<Msg> for Counter { fun body(self, ui: Ui<Msg>) -> View { … } }` | One `View` type instead of `some View`: there are no opaque or existential types |
| `VStack { A; B }` | `vstack([a, b])` | Children are a list literal; a trailing comma is fine |
| `VStack(alignment: .leading, spacing: 8) { … }` | `vstack([…]).spacing(8).align(Alignment.Leading)` | No named arguments, so settings are modifiers |
| `Text("Hi").font(.title).padding()` | `text("Hi").font(Font.Title).padding(8)` | Methods on `View` |
| A modifier on its own line | Works inside `[ ]` and `( )`; the outermost view is wrapped in `( )` | [[MYLA-589]] removes the parentheses |
| `if big { Text("big") }` | `if big { text("big") } else { empty() }`, or `when(big, text("big"))` | An `if` value needs an `else` |
| `ForEach(items) { Row($0) }` | `for_each(items, (it) => it.id, (it) => row(it))` | The key gives each row its identity |
| `@State var count = 0` | A field of the model | A view's own state needs a cell ([[Project/GUI-plan/Gaps]], L1); sketched below |
| `Button("+") { count += 1 }` | `button("+", ui.send(Msg.Increment))` | A closure can't change state (D93); the action is a message |
| `TextField("Name", text: $name)` | `text_field("Name", self.name, ui.send_text((s) => Msg.Rename(s)))` | A binding is a value and a message for its change |
| `.onAppear { … }`, `.task { … }` | `.on_appear(ui.send(Msg.Appeared))`, `ui.perform(job, (r) => Msg.Loaded(r))` | Effects come back as messages |
| `.environment(\.theme, t)` | `.environment(t)` | Keyed by the value's type or by a key value |
| `@main struct MyApp: App { … }` | `#main async fun main() { await ui.run(Counter { … }) }` | |

## A program that runs

A small framework core and a counter, complete. It prints the view tree instead of drawing it and presses the buttons from `main`; a real core would lay the tree out and wait for events. It shows that the whole shape type-checks today: one non-generic `View`, modifiers in a chain, a typed model with messages, actions erased by closures, a text binding, a conditional child.

```myla
// ---- the framework's side ----------------------------------------------
#derive(Eq)
enum Font { Body, Title }

struct Action { next: () -> Root }
struct TextAction { next: (str) -> Root }

enum Kind {
    Text(str)
    Button(str, Action)
    Field(str, TextAction)
    Stack(bool, [View])
    Empty
}

struct View { kind: Kind, pad: int, font: Font }
struct Root { view: View }

fun view_of(k: Kind) -> View { return View { kind: k, pad: 0, font: Font.Body } }
fun text(s: str) -> View { return view_of(Kind.Text(s)) }
fun button(label: str, a: Action) -> View { return view_of(Kind.Button(label, a)) }
fun text_field(value: str, a: TextAction) -> View { return view_of(Kind.Field(value, a)) }
fun vstack(children: [View]) -> View { return view_of(Kind.Stack(true, children)) }
fun hstack(children: [View]) -> View { return view_of(Kind.Stack(false, children)) }
fun empty() -> View { return view_of(Kind.Empty) }

impl View {
    fun padding(self, n: int) -> View { return View { kind: self.kind, pad: n, font: self.font } }
    fun font(self, f: Font) -> View { return View { kind: self.kind, pad: self.pad, font: f } }
}

trait Model<M> {
    fun update(var self, msg: M)
    fun body(self, ui: Ui<M>) -> View
}

// What a body makes its actions with: `wrap` turns a message into the
// closure that gives the next root.
struct Ui<M> { wrap: (M) -> Action }

impl<M> Ui<M> {
    fun send(self, msg: M) -> Action {
        let w = self.wrap
        return w(msg)
    }

    fun send_text(self, f: (str) -> M) -> TextAction {
        let w = self.wrap
        return TextAction { next: (s: str) => {
            let n = w(f(s)).next
            return n()
        } }
    }
}

// The model `s` as a root: its view, whose actions hold `s` and give the
// root of the model after their message.
fun root_of<S: Model<M>, M>(s: S) -> Root {
    let ui: Ui<M> = Ui { wrap: (m: M) => Action { next: () => {
        var t = s
        t.update(m)
        return root_of<S, M>(t)
    } } }
    return Root { view: s.body(ui) }
}

// ---- the program's side ------------------------------------------------
enum Msg { Increment, Decrement, Rename(str) }

struct Counter { name: str, count: int }

impl Model<Msg> for Counter {
    fun update(var self, msg: Msg) {
        match msg {
            Increment => { self.count += 1 }
            Decrement => { self.count -= 1 }
            Rename(s) => { self.name = s }
        }
    }

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
            if self.count > 1 { text("big") } else { empty() },
        ])
    }
}

// ---- a stand-in for the window: the tree as text, events by hand --------
fun show(v: View, depth: int) -> str {
    let ind = "  ".repeat(depth)
    return match v.kind {
        Text(s) => ind + "Text " + s + (if v.font == Font.Title { " (title)" } else { "" }) + "\n"
        Button(l, _) => ind + "Button " + l + "\n"
        Field(s, _) => ind + "Field " + s + "\n"
        Stack(vertical, kids) => {
            var out = ind + (if vertical { "VStack" } else { "HStack" }) + f" padding {v.pad}\n"
            for k in kids {
                out = out + show(k, depth + 1)
            }
            out
        }
        Empty => ""
    }
}

fun press(v: View, label: str) -> Option<Root> {
    match v.kind {
        Button(l, a) => {
            if l != label { return None }
            let n = a.next
            return Some(n())
        }
        Stack(_, kids) => {
            for k in kids {
                if let Some(r) = press(k, label) { return Some(r) }
            }
            return None
        }
        _ => { return None }
    }
}

fun type_text(v: View, s: str) -> Option<Root> {
    match v.kind {
        Field(_, a) => { return Some(a.next(s)) }
        Stack(_, kids) => {
            for k in kids {
                if let Some(r) = type_text(k, s) { return Some(r) }
            }
            return None
        }
        _ => { return None }
    }
}

fun main() {
    var root = root_of<Counter, Msg>(Counter { name: "apples", count: 0 })
    root = press(root.view, "+").expect("a + button")
    root = press(root.view, "+").expect("a + button")
    root = type_text(root.view, "pears").expect("a text field")
    print(show(root.view, 0).trim_end())
}
// output:
// VStack padding 0
//   Text pears: 2 (title)
//   HStack padding 8
//     Button -
//     Button +
//   Field pears
//   Text big
```

What the program shows about the language:

- **The tree's type is one struct.** `Kind` is a recursive enum through `[View]`; closures in its variants erase the model's and the message's types. Nothing in `View` is generic, so `text("x").font(f)` needs no annotation.
- **`root_of` is the only generic function**, and it is the framework's. The program's side has no type arguments except the one call that starts it, which `ui.run(model)` would hide.
- **`update` is an ordinary `var self` method** and `body` an ordinary function of `self`: both take `#test` cases.
- **A function-typed field is called through a `let`** (`let n = a.next`) or directly (`a.next()`); the program uses both.

## The modifiers

A modifier is a method on `View` that returns a changed copy. Inside a child list the chain breaks before the dot, as in SwiftUI:

```myla fragment
vstack([
    text("Title")
        .font(Font.Title)
        .foreground(Color.Accent),
    image("logo.png")
        .frame(64, 64)
        .corner_radius(8),
])
```

The outermost view of a `body` isn't inside brackets, so its chain is wrapped until [[MYLA-589]]:

```myla fragment
return (vstack([
    …
])
    .padding(16)
    .background(Color.Window))
```

Modifiers with several optional settings take defaults from the end (`.frame(width, height)`, `.shadow(radius, x = 0, y = 2)`), or a small style value built by its own chain (`.border(stroke().width(2).color(Color.Red))`), as `std.term`'s `style().fg(c).bold()` is.

A program's own modifier is a function, used with a pipe, which continues a line when it ends it:

```myla fragment
fun card(v: View) -> View {
    return v.padding(12).background(Color.Surface).corner_radius(10)
}

text("Balance") |> card()
```

## A program's own views

A view of the program's is a function that returns a `View`; its inputs are its parameters:

```myla fragment
fun price_row(item: Item, on_remove: Action) -> View {
    return hstack([
        text(item.name),
        spacer(),
        text(f"{item.price:.2}"),
        button("Remove", on_remove),
    ])
}

// in the parent's body:
for_each(self.items, (it) => it.id, (it) => price_row(it, ui.send(Msg.Remove(it.id))))
```

A sub-view with a model and messages of its own is embedded by wrapping its messages, as in Elm:

```myla fragment
// Settings is a Model<SettingsMsg>; the parent's message has a variant for it
ui.child(self.settings, (m) => Msg.Settings(m))
```

## Names

Two spellings are possible today, because a function's name may be capitalised (tried: `fun Text(s: str) -> View` checks):

| | Lower-case functions | Capitalised functions |
| --- | --- | --- |
| Looks like | `vstack([text("a"), button("b", act)])` | `VStack([Text("a"), Button("b", act)])` |
| For | Myla's convention: a call that starts lower-case is a function, a capitalised name a type or a variant | It reads as SwiftUI does |
| Against | Further from SwiftUI | `Text` isn't a type: `let t: Text` fails, and `Text { … }` isn't its literal. A reader can't tell a view from an enum variant such as `Some(x)` |

Recommended: lower-case now. Tier 3's `view` declaration makes views types, and then the capitalised names are true ([[Project/GUI-plan/Syntax-with-grammar-change]]).

## With a cell primitive, still without a grammar change

If std gets a shared cell (the smallest answer to L1 on [[Project/GUI-plan/Gaps]]), a view can keep state of its own and an action can be a closure, with no message type. The grammar stays as it is; this is a library change over one new primitive:

```myla fragment
fun counter(ui: Ui, title: str) -> View {
    let count = ui.state(0)                       // a State<int>, kept by this view's identity
    let name = ui.state("apples")
    return vstack([
        text(f"{title}: {count.get()}")
            .font(Font.Title),
        hstack([
            button("-", () => count.set(count.get() - 1)),
            button("+", () => count.set(count.get() + 1)),
        ]),
        text_field("Name", name),                 // the handle is the binding
        when(count.get() > 9, text("big")),
    ])
}
```

- `count.set(…)` inside the lambda is allowed: the lambda doesn't change `count`, a handle it copied; it calls a method that isn't `var self`, as `ch.send(x)` on a channel is.
- `ui.state(0)` finds its cell by the view's identity and the order of the calls in the body, as React's hooks do; the rule that comes with it is that `ui.state` isn't called in a branch or a loop. A `view` declaration (tier 3) removes that rule, because the state is declared, not called for.
- A handle passed to a child is SwiftUI's `Binding`.

## What stays awkward without new syntax

In the order it would be felt:

1. **No labels on arguments.** `slider(self.volume, 0.0, 100.0, 1.0, …)` says nothing about which number is the step.
2. **`else { empty() }`** on every conditional child, and `for_each` with two lambdas for every loop.
3. **Parentheses around the outermost chain** (until [[MYLA-589]]).
4. **`Font.Title`, `Color.Red`, `Alignment.Leading`** in full everywhere.
5. **Commas and brackets** around children.
6. **A message type and an `update` method** for a counter. It is the right structure for a large app and ceremony for a small one.

Tier 1 of [[Project/GUI-plan/Syntax-with-grammar-change]] answers 1 to 4, tier 2 answers 5, tier 3 (or the cell) answers 6.
