# Styling

How a Myla GUI gets its look, and how a program changes it. Part of [[Project/GUI-plan]]; a follow-up to the owner's question of 18 November 2026.

[TOC]

## SwiftUI's model, which is the proposal

SwiftUI has no style sheets. A look comes from four things, and all four translate to Myla:

| Mechanism | SwiftUI | Myla |
| --- | --- | --- |
| Modifiers | `.font(.title).foregroundStyle(.red).padding()` | The same chain; methods on `View` |
| Inheritance down the tree | `.font(…)` on a stack applies to the texts inside | Inherited attributes in the environment |
| Control styles | `.buttonStyle(.bordered)`, a type conforming to `ButtonStyle` | A function from the control's state to a view |
| A theme | Semantic colours, text styles, the system's light and dark | A `Theme` value in the environment |

Why not CSS-like sheets with selectors: they are a second language with its own cascade, matched by strings the checker can't see, and they style by a tree's shape, which a refactoring changes. Named styles (below) give the one thing sheets are loved for, changing a look in one place, as values.

## Tokens: the theme

A theme is a struct of named values. Controls never hold a colour; they hold a role.

```myla fragment
#derive(Eq, Toml)
pub struct Theme {
    colors: Colors,          // window, surface, text, secondary_text, accent, on_accent, border, danger, …
    text: TextStyles,        // body, title, headline, caption, mono: family, size, weight, line height
    spacing: Spacing,        // xs, s, m, l, xl
    radius: Radii,           // control, card, sheet
    control: ControlSizes,   // heights, paddings, the minimum target
    motion: Motion,          // durations and curves
}
```

- **Semantic names.** `Color.Accent`, `Color.Surface`, `Font.Title`: a view names a role, the theme gives the value. A literal is still possible (`Color.rgb(…)`).
- **Light and dark** are two themes; `ui.system()` follows the system's setting where the platform tells it, and `.theme(t)` sets one for a subtree.
- **A theme is data.** With `#derive(Toml)` it loads from a file; the probe decoded one with `toml.decode<Theme>(…)`. So a program can ship themes as files, a user can edit one, and a running program can reload it when the file changes, with no rebuild.
- **Size and density.** One scale factor on the text styles is the user's text size; one on spacing and control sizes is density (compact for a mouse, roomy for touch). Layout is in points, the window's scale turns them into pixels.
- **High contrast and reduced motion** are theme variants the system setting selects.

## Inherited attributes

Some modifiers set a value for everything below them: font, foreground colour, tint, control size, whether controls are enabled, the text's alignment, the layout direction. They live in the environment the rebuild carries down, so:

```myla fragment
vstack([
    text("Title").font(Font.Title),     // its own
    text("One"),                        // caption, secondary
    text("Two"),                        // caption, secondary
])
    .font(Font.Caption)
    .foreground(Color.SecondaryText)
```

Which modifiers inherit and which wrap (padding, background, frame, border apply to the one view) is fixed and documented per modifier, as in SwiftUI.

## Control styles

A control is behaviour plus a look. The look is a function from the control's state to a view, which the theme reaches through the environment. No trait objects are needed: a function value is the erased thing.

```myla fragment
pub struct ButtonState { label: View, pressed: bool, hovered: bool, focused: bool, enabled: bool, role: ButtonRole }

pub typealias ButtonStyle = (ButtonState) -> View

fun pill(s: ButtonState) -> View {
    return themed((t) => s.label
        .padding_xy(t.spacing.m, t.spacing.s)
        .background(if s.pressed { t.colors.accent.darker(0.1) } else { t.colors.accent })
        .foreground(t.colors.on_accent)
        .corner_radius(999)
        .opacity(if s.enabled { 1.0 } else { 0.4 }))
}

// for one button, or for every button below
button("Save", ui.send(Msg.Save)).button_style(pill)
vstack([…]).button_style(pill)
```

- **States are parameters.** Hover, pressed, focused, disabled, selected: the style function gets them and decides. There are no pseudo-classes.
- **Every control has one**: `toggle_style`, `text_field_style`, `slider_style`, `list_row_style`, … The framework's defaults are written the same way, in the same public API, so a program can read them and copy one.
- The probe built a button's look from a state and a theme this way; it checks and runs today.

## Named styles

For "all primary buttons look like this" across a program, a style is a value with a name, not a class string:

```myla fragment
// the program's own design system: plain functions and constants
pub fun primary(v: View) -> View { return v.button_style(pill).control_size(ControlSize.Large) }
pub fun card(v: View) -> View { return v.padding(12).background(Color.Surface).corner_radius(10).shadow(8) }

button("Buy", buy) |> primary()
vstack([…]) |> card()
```

The checker sees every use; "find references" lists them; renaming works. A program's design system is a module of such functions.

If themes should restyle named things without code (a designer's wish), a second step is styles the theme carries by key: `.style("card")` looks up a `Style` value (a struct of optional paddings, colours, radii, fonts) in `theme.styles`. It costs the checker's help, so it is an option, not the default.

## Platform look

Myla draws its own pixels, so no program looks native by itself. The choices:

| Choice | Result |
| --- | --- |
| One default theme, Myla's own, the same everywhere (recommended first) | A Myla program is recognisable, as a Flutter or an Electron program is; pictures are the same on every target |
| Themes that follow each platform's look | Close to native at a glance, never exact, and work for each system's every release |
| Follow the system's settings only | The accent colour, light or dark, text size, the font, reduced motion: cheap, and what users notice most |

What must follow the platform regardless of the look, because users feel it: keyboard shortcuts (Ctrl or Cmd), the order of dialog buttons, scrolling physics, text editing keys, where menus are.

## Drawing beyond the controls

- **Shapes**: `rectangle()`, `rounded(8)`, `circle()`, `path(…)` with `.fill(…)` and `.stroke(…)`; a shape is a view.
- **A canvas**: `canvas((c, size) => { … })` gives a drawing context that records into the display list, for charts and custom controls.
- **Fills** are a colour, a gradient or an image; shadows and blurs are modifiers, with the cost of a blur said in the docs (the software renderer does it on the CPU).

## Animation of style

A style change can animate because the framework compares old and new values per element: `.animation(Curve.EaseOut, 200)` on a view interpolates its colours, sizes, offsets and opacity between rebuilds. The durations and curves come from the theme (`motion`), so reduced motion is one switch. Animation is a later phase; the element tree is designed to hold it.

## What the language lacks for it

| Gap | Effect on styling | On |
| --- | --- | --- |
| No `.title` for an expected enum | `Font.Title`, `Color.Accent` in full | Tier 1c, [[Project/GUI-plan/Syntax-with-grammar-change]] |
| No named arguments | `.shadow(8, 0, 2)`; `.padding_xy(a, b)` instead of `.padding(horizontal: a)` | Tier 1a |
| No struct field defaults, no copy-with | A theme derived from another names every field; `Style` values with many optional fields are builder chains | [[Project/GUI-plan/Gaps#l6-smaller-ones]], [[Project/GUI-plan/Data-bindings]] |
| No trait default bodies | A program's own view type doesn't get the modifiers; styles are functions on `View` | [[Project/GUI-plan/Gaps#l4-no-trait-default-bodies]] |
| `#derive(Toml)` has no defaults for missing keys | A theme file must name every value, or the theme is all `Option`s | A `#derive(Toml)` extension, or themes as overrides applied to a base in code |
| No embedded files | The default font and icons | [[Project/GUI-plan/Gaps#l6-smaller-ones]] |

## To decide

1. The default look: Myla's own everywhere, or per platform.
2. Whether keyed styles in the theme (`.style("card")`) exist at all, or only functions.
3. The token set: which colours, text styles and sizes are in `Theme` from the start; adding is easy, renaming breaks every theme file.
4. Units: points with a scale (recommended), and whether text sizes scale apart from the rest.
