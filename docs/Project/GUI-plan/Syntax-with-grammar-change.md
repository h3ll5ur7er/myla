# Syntax with grammar change

Grammar changes that would bring Myla's GUI code close to SwiftUI's, in three tiers. Each tier works without the next, and tier 1 is useful to programs that never open a window. Part of [[Project/GUI-plan]]; what works with today's grammar is on [[Project/GUI-plan/Syntax-without-grammar-change]].

Every form below is a parse error today (tried at `dd57b05`: `f(1, y: 3)`, `g(.Title)`, `[1, if c { 2 }]`, `f(1) { … }`), so none changes the meaning of a program that checks now. Every new word would be a soft keyword, as `defer` is.

[TOC]

## The same view in each tier

Today:

```myla fragment
fun body(self, ui: Ui<Msg>) -> View {
    return (vstack([
        text(f"{self.name}: {self.count}")
            .font(Font.Title),
        hstack([
            button("-", ui.send(Msg.Decrement)),
            button("+", ui.send(Msg.Increment)),
        ]),
        if self.count > 9 { text("big") } else { empty() },
        for_each(self.tags, (t) => t, (t) => text(t)),
    ])
        .spacing(8)
        .padding(16))
}
```

Tier 1 (named arguments, `if` and `for` as elements, `.title`, leading-dot continuation):

```myla fragment
fun body(self, ui: Ui<Msg>) -> View {
    return vstack(spacing: 8, [
        text(f"{self.name}: {self.count}")
            .font(.title),
        hstack([
            button("-", ui.send(.Decrement)),
            button("+", ui.send(.Increment)),
        ]),
        if self.count > 9 { text("big") },
        for t in self.tags { text(t) },
    ])
    .padding(16)
}
```

Tier 2 (trailing blocks that collect views):

```myla fragment
fun body(self, ui: Ui<Msg>) -> View {
    return vstack(spacing: 8) {
        text(f"{self.name}: {self.count}")
            .font(.title)
        hstack {
            button("-", ui.send(.Decrement))
            button("+", ui.send(.Increment))
        }
        if self.count > 9 {
            text("big")
        }
        for t in self.tags {
            text(t)
        }
    }
    .padding(16)
}
```

Tier 3 (a `view` declaration with `state`):

```myla fragment
view Counter(name: str, tags: [str]) {
    state count = 0

    body {
        VStack(spacing: 8) {
            Text(f"{name}: {count}")
                .font(.title)
            HStack {
                Button("-") { count -= 1 }
                Button("+") { count += 1 }
            }
            if count > 9 {
                Text("big")
            }
            for t in tags {
                Text(t)
            }
        }
        .padding(16)
    }
}
```

## Tier 1: small general features

Four changes. None is about GUIs; each is a parser desugaring or a checker rule on existing nodes, the cheap kind in the feature checklist.

### 1a. Named arguments

```myla fragment
fun slider(value: float, from: float = 0.0, to: float = 1.0, step: float = 0.0) -> View

slider(self.volume, to: 100.0, step: 1.0)
vstack(spacing: 8, children)
```

- An argument may be written `name: value`. Positional arguments come first; named ones follow in any order; a parameter with a default may be left out anywhere, not only at the end (which lifts D136's "trailing only").
- The name is the parameter's name. There are no separate labels as in Swift (`func f(at index: Int)`): one name is one thing less to learn.
- A function value has no names (`let f = slider` is called positionally), as it has no defaults today.
- **Grammar:** in a call's argument list, `IDENT ':' expression`. A lambda starts with `(`, a map literal with `[`, so `IDENT ':'` after `(` or `,` in a call can't be anything else.
- **Encoding:** the checker reorders the arguments and fills the defaults where it fills defaults today (`fill_in`), so the interpreter and the backends see a whole positional call.
- **To decide:** whether renaming a parameter then breaks callers (yes, as in Swift, Kotlin and Python), and whether a `pub` function may opt out.

### 1b. `if` and `for` as elements of a list literal

```myla fragment
let children = [
    header(),
    if self.editing { toolbar() },          // one element or none
    for item in self.items { row(item) },   // one element for each
    footer(),
]
```

- In a list literal, an element may be an `if` without `else` (nothing when the condition is false; with an `else if` chain, the first branch that holds) or a `for` (its block's value, once per turn). A branch's or the block's value is one element; a nested literal isn't spread.
- This is Dart's collection `if` and `for`, added to Dart for Flutter for the reason it is proposed here. It serves any list: arguments for a command line, rows of a table, routes.
- **Encoding:** the parser rewrites the literal into a pushed-to list, with nodes that exist.
- It also works in a map literal (`["a": 1, if c { "b": 2 }]`); that half can wait.

### 1c. A variant by its name alone where its enum is expected

```myla fragment
text("Title").font(.title).foreground(.red)
button("+", ui.send(.Increment))
let a: Alignment = .leading
```

- `.Name` and `.Name(args)` in an expression construct a variant of the enum the context expects: a parameter's type, an annotated `let`, a field, a `return`. Patterns have had `.V` since the start; this is its other half.
- Where no enum is expected (`let x = .Red`), it is an error that says so.
- Lower-case `.title` as in the examples needs nothing more if the enum's variants are named so; Myla's variants are capitalised by convention, so by that convention it is `.Title`. To get SwiftUI's `.title` on a struct such as `Font` (which isn't an enum there), a trait's function without `self` would also have to be reachable this way (`Font.title()` as `.title()`); that is an extension to keep for later.
- **Grammar:** `'.' IDENT` in prefix position (where an expression starts). A dot after an expression stays a field or method. With [[MYLA-589]]: a line that *starts* with a dot continues the line before it, so a statement can't start with an implicit variant, which would be a useless statement anyway. In a `match`'s arm list, [[MYLA-589]]'s rule for `.V =>` patterns stands.

### 1d. Leading-dot continuation

[[MYLA-589]], unchanged. Listed here because the examples rely on it for the outermost view.

### What tier 1 costs and gives

Four parser changes, two with a checker rule, no new node kind that reaches the backends, no new keyword. It removes four of the six awkward points on [[Project/GUI-plan/Syntax-without-grammar-change]], and named arguments change the shape of every framework function, so tier 1 belongs before the API is published.

## Tier 2: trailing blocks

```myla fragment
vstack(spacing: 8) {
    text("a")
    if c {
        text("b")
    }
}

button("Save") {
    ui.send(.Save)
}
```

A call may be followed, on the same line, by a block that becomes its last argument. What the block means follows from the last parameter's type:

| The last parameter's type | The block is | Example |
| --- | --- | --- |
| A list `[T]` | A **collecting block**: every expression statement of type `T` (or `[T]`) is added to the list, in order; `let`, `if`, `for`, `match` and `while` are ordinary statements, and their blocks collect too | `vstack { … }` |
| A function type `() -> R` | A **lambda's body**: `f(x) { … }` is `f(x, () => { … })` | `button("Save") { … }`, `task.timeout(500) { … }` |
| A function type with parameters | A lambda whose parameters are written first: `{ (it) => … }` stays the explicit form; a short form is to decide | `for_each(items) { (it) => row(it) }` |

- Without arguments the parentheses may be left out: `hstack { … }`.
- **Where it isn't allowed:** in the head of `if`, `while`, `for` and `match`, where `{` starts the body. That is the rule struct literals have there today, and the same way out: parentheses.
- **`Name { … }` and struct literals.** `Point { x: 1, y: 2 }` is a struct literal; `hstack { text("a") }` a call with a block. The parser can tell them apart by the first tokens after `{` (`IDENT ':'` or `}` is a literal), and the checker knows whether the name is a struct or a function. With lower-case functions and capitalised types the reader can tell too.
- **Encoding:** the parser keeps a trailing-block node; the checker, which knows the callee's last parameter, rewrites it into a lambda or into a pushed-to list (1b's rewrite). The backends see neither.
- **What it is not:** Swift's result builders, where a type decides how statements combine. Here there is one rule, "collect into the list", which is what every SwiftUI container does with its content. A program's own container is a function whose last parameter is `[View]`.

Tier 2 is where the code starts to read as SwiftUI. It is also the first change that gives a block a meaning that depends on the callee's type, which no Myla construct does today, so it deserves a round of its own after tier 1 has been used.

## Tier 3: a `view` declaration

```myla fragment
view Counter(title: str) {
    state count = 0
    state name = "apples"

    body {
        VStack(spacing: 8) {
            Text(f"{title}: {count}")
            Button("+") { count += 1 }
            TextField("Name", text: name)
            Stepper(value: count, in: 0..10)
        }
    }

    fun reset(var self) {
        count = 0
    }
}

// used as any view:
Counter(title: "Apples")
```

A `view` is a declaration of its own, as `actor` is:

- **Parameters** in its head are its inputs, set by the parent on every rebuild, immutable inside: `Counter(title: "Apples")`. A view is called by its name, which is a type's name, so it is capitalised; the built-in views become `Text`, `VStack`, `Button` and the names are true.
- **`state name = initial`** declares state that belongs to this view's place in the tree and survives its parent's rebuild. Inside the view it reads as a variable.
- **`body { … }`** is a collecting block (tier 2) that gives the view's content. It may only read.
- **An action block** (`Button("+") { count += 1 }`) may assign state. This is the one place where a closure changes something: the compiler turns the block into a function over the view's state, and the framework calls it with the stored state and stores the result. The rule D93 protects stays whole: nothing is changed through a copy.
- **A state passed to a child** where the child's parameter is declared `binding` (`view TextField(label: str, binding text: str)`) passes the place, not the value: SwiftUI's `$name`, without the `$`.
- **Methods** with `var self` are named actions (`Button("Reset", action: reset)`).

**What it lowers to.** A struct of the parameters, a struct of the state, a `body` function of both, and a function per action over the state struct: the model with messages of [[Project/GUI-plan/Architecture]], written by the compiler, with the messages being the action functions. The state struct is stored by the framework per identity, which needs the type-erased storage of [[Project/GUI-plan/Gaps]] (L1): tier 3 doesn't remove that need, it hides it.

**Why a declaration and not general features.** Swift reaches the same surface with property wrappers, result builders, opaque types and key paths: four general features, each large, whose interplay is most of what is hard about SwiftUI's errors. A dedicated declaration is one feature with one set of messages ("`count` is state of `Counter` and can only be assigned in an action"), as `actor` gave isolation without a general ownership system. The price is that it serves GUIs only.

**The alternative in general features**, for comparison: cells (L1), `var` parameters on lambdas or `ref` capture (D15), tier 2's blocks. Then a view is a function, state is `ui.state(0)`, and an action is `{ count.set(count.get() + 1) }`. It needs no `view` keyword, and reads a step further from SwiftUI:

```myla fragment
fun counter(ui: Ui, title: str) -> View {
    let count = ui.state(0)
    return vstack(spacing: 8) {
        text(f"{title}: {count.get()}")
        button("+") { count.set(count.get() + 1) }
    }
}
```

## Comparison

| | Today | Tier 1 | Tier 2 | Tier 3 |
| --- | --- | --- | --- | --- |
| Labels on arguments | no | yes | yes | yes |
| Conditional and repeated children | `else { empty() }`, `for_each` | `if`, `for` in the list | statements | statements |
| Brackets and commas around children | yes | yes | no | no |
| `.title` | no | yes | yes | yes |
| A view's own state | no (model only) | no | no | yes |
| An action as a block that assigns | no | no | no | yes |
| New syntax | – | 4 small forms | + trailing blocks | + `view`, `state`, `body`, `binding` |
| Serves code that isn't a GUI | – | all of it | most (`f(x) { … }`) | none |
| Needs L1 (type-erased storage) | no | no | no | yes |
| Compiler work | none | parser, `fill_in`, one checker rule | a node the checker rewrites | a declaration through loader, checker and a lowering to structs and functions; language server, grammar, docs |

## Recommendation

1. **Build the core without any grammar change** (phase 2 of [[Project/GUI-plan]]), to learn what hurts in real programs.
2. **Tier 1 before the framework's API is published.** It is small, general, and the only tier whose absence would force a breaking change later.
3. **Tier 2 after a few real programs exist**, if brackets and commas turn out to be what bothers.
4. **Tier 3 only together with the decision on type-erased storage**, and only if the model with messages proves too heavy for small programs. The cell-based alternative gets most of the way with one primitive and no keyword.
