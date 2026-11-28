# Data bindings

How a control reads and writes a piece of the program's state: SwiftUI's `$name`. Part of [[Project/GUI-plan]]; a follow-up to the owner's question of 18 November 2026.

[TOC]

## What a binding is

A binding is a value and a way to change it, handed to a control so that the control doesn't know where the value lives. SwiftUI has three sources (`@State`, `@Binding`, `@Bindable` for observable objects) and one type, `Binding<Value>`, with `get` and `set`.

Myla's version depends on the state model ([[Project/GUI-plan/Architecture#state-and-effects]]):

| State model | A binding is | Made by |
| --- | --- | --- |
| Model with messages | The current value and a function from a new value to an action | `ui.bind(self.name, (s) => Msg.SetName(s))` |
| State cells | The cell's handle itself | `text_field("Name", name)` |
| `view` declaration (tier 3) | A place of the view's state | `TextField("Name", text: name)` where the parameter is declared `binding` |

## With today's language

Tried on 2026-11-18 at `4ad9493` (interpreted and native give the same):

```myla fragment
struct Binding<T> { value: T, set: (T) -> Action }

impl<M> Ui<M> {
    fun bind<T>(self, value: T, msg: (T) -> M) -> Binding<T> {
        let w = self.wrap
        return Binding { value: value, set: (x: T) => w(msg(x)) }
    }
}

// controls take a binding of their value's type
fun toggle(label: str, b: Binding<bool>) -> View
fun text_field(label: str, b: Binding<str>) -> View
fun slider(b: Binding<float>, from: float, to: float) -> View

// in a body:
toggle("Dark", ui.bind(self.dark, (b) => Msg.SetDark(b)))
text_field("Name", ui.bind(self.name, (s) => Msg.SetName(s)))
```

- **`Binding<T>` is generic, `View` isn't.** Each control fixes `T`, so nothing has to be inferred through a chain ([[Project/GUI-plan/Gaps#l3-inference-through-a-method-chain]]).
- **One-way is the default.** A control that only shows takes the value (`text(self.name)`); one that edits takes a binding. There is no hidden two-way link, and no observation: after `set`, the model changes and `body` runs again.
- **A binding is typed end to end.** `ui.bind(self.age, (s) => Msg.SetName(s))` is a type error at the lambda.

### Conversions

A text field for a number, a slider for a percentage, a picker for an enum: the binding is mapped both ways. The way back gets the old value for input that doesn't convert:

```myla fragment
impl<T> Binding<T> {
    fun map<U>(self, to: (T) -> U, back: (U, T) -> T) -> Binding<U>
}

let age = ui.bind(self.age, (n) => Msg.SetAge(n))
text_field("Age", age.map<str>((n) => f"{n}", (s, old) => num.parse_int32(s).unwrap_or(old)))
```

In the probe, typing `41` and then `abc` into that field leaves the model at 41. A real field keeps the text being typed in the element tree and shows the error; the framework would ship the common pairs (`age.as_text()`, `ratio.as_percent()`).

### Derived and constant bindings

- `binding.constant(v)`: a value nothing changes (previews, disabled controls).
- `b.on_change((new) => Msg.Validate(new))`: a second message after the first.
- A binding to an element of a list is a binding with the index or the key in its message: `ui.bind(item.done, (d) => Msg.SetDone(item.id, d))`.

## What is awkward, and what would help

**1. A message per field.** A form with twelve fields has twelve variants and twelve arms in `update` that each assign one field. Four ways out, smallest first:

| Way | Looks like | Needs |
| --- | --- | --- |
| A message that carries the whole sub-struct | `ui.bind(self.settings, (s) => Msg.Settings(s))`, then `form.field(…)` per field | A way to write "this struct with one field changed"; today that is a literal naming every field |
| A copy-with expression | `Settings { ..s, name: v }` or `s.with(name: v)` | A small grammar change (struct update is the one piece of Rust's struct syntax Myla left out) |
| Derived setters | `#derive(Lens)` gives each field a function pair; `ui.field(Settings.name)` | A derive that generates named functions, and trait functions as values |
| Places as values | `ui.bind(self.settings.name)`: the compiler turns a place expression into the get and set pair | A language feature (Swift's key paths); the model must be reachable as `var` by the framework |

The copy-with expression is the smallest general feature and would join tier 1 of [[Project/GUI-plan/Syntax-with-grammar-change]]. Places as values is what makes bindings disappear into the syntax, and is what a `view` declaration's `binding` parameters do for a view's own state.

**2. An enum variant isn't a function value**, so `(s) => Msg.SetName(s)` can't be written `Msg.SetName`. Allowing a variant with a payload where a function type is expected is a checker change of a few lines and no grammar change; it would shorten every binding on this page.

**3. With cells there is no ceremony at all**: the handle is the binding, a child gets a copy of the handle, `map` works the same. That is the strongest argument for cells ([[Project/GUI-plan/Gaps#l1-type-erased-storage]]).

## Collections

- **Identity.** `for_each(items, key, row)`: the key ties a row's element (its focus, its text cursor, its animation) to the item, not to the position.
- **Editing in a row** is a binding with the key in its message, as above.
- **Selection** is a binding to a key or a set of keys: `list(items, key, row).selection(ui.bind(self.selected, (k) => Msg.Select(k)))`.
- **Large lists.** The model holds the data; the list control builds rows only for what is visible, so `body` gives a row function, not ten thousand views.

## Validation, formatting, undo

- **Validation** belongs in `update`: the message arrives, the model decides, the body shows the error beside the field. Nothing to add to bindings.
- **Formatting** is `map` with a format and a parser; `std.num`, `std.time` and `std.fmt` have both directions.
- **Undo** falls out of values: the framework (or the program) keeps earlier models. `ui.run(model).undoable(50)` is a list of 50 structs sharing what didn't change (copy-on-write).

## Not proposed

- **Observation** (a control subscribes to a property and is told of changes). The rebuild-and-compare model makes it unnecessary, and it needs shared mutable objects.
- **Two-way bindings between two pieces of state.** One of them is derived; compute it in `body` or in `update`.
