# Dependency injection

How code gets the services it uses (a clock, an HTTP client, a store, a logger) without naming who provides them, so that a test, a preview or another platform can provide something else. The owner's idea of 18 November 2026: it would serve more than the GUI. Part of [[Project/GUI-plan]].

[TOC]

## Where Myla stands

Myla has no global variables, no trait objects and no reflection, so the two usual mechanisms don't exist: a global registry ("service locator") and a container that builds objects from their constructors' types at run time. What it has instead is that **every dependency is already a parameter**: a function can only reach what it was given. Injection in Myla isn't about making dependencies visible, it is about making the passing cheap and the swapping possible.

Two things work against that today:

- **The standard library's effects are free functions.** `time.now_ms()`, `fs.read_to_string(p)`, `http.get(url)`, `random.seeded(n)`: a function that calls them can't be given others. The `Read` and `Write` traits are the exception, and the model to follow.
- **Passing is by hand**, through every function between the one that provides and the one that uses.

## Three forms that work today

All three ran on 2026-11-18 at `c507ef2`, under `myla run`, `myla test` and natively.

### 1. A record of functions

A service is a struct whose fields are functions; a provider is any value of it. The closures erase who is behind it, so a real client, a fake and an actor all fit the same type.

```myla fragment
struct Clock { now_ms: () -> int64 }
struct Http { get: async (str) -> Result<str, str> }
struct Store { save: async (str) -> int, count: async () -> int }
struct Deps { clock: Clock, http: Http, store: Store }

// a real service that is an actor, behind the record
fun store_of(n: Notes) -> Store {
    return Store { save: async (s: str) => await n.add(s), count: async () => await n.size() }
}

// the code names what it needs
async fun fetch_and_save(d: Deps, url: str) -> Result<str, str> {
    let body = (await d.http.get(url))?
    let n = await d.store.save(body)
    return Ok(f"{n} saved at {d.clock.now_ms()}: {body}")
}

#test
async fun saves_what_it_fetched() {
    let d = Deps {
        clock: Clock { now_ms: () => 1000i64 },
        http: Http { get: async (url: str) => if url == "ok" { Ok("hello") } else { Err("no route to " + url) } },
        store: store_of(Notes { items: [] }),
    }
    expect(await fetch_and_save(d, "ok") == Ok("1 saved at 1000: hello"))
    expect(await fetch_and_save(d, "bad") == Err("no route to bad"))
    expect(await d.store.count() == 1)
}
```

- A field that holds a function is called like a method (`d.http.get(url)`, D178), so the use site reads as an object's.
- It is the only form that covers **async services** and **actors**: a trait can't have async methods ([[MYLA-434]]) and `impl Saver for Notes` on an actor is `an actor can't implement a trait`.
- One `Deps` struct for the program keeps signatures short: one parameter, not five.
- The cost: a record per service written by hand beside its implementation, an indirect call, and a struct literal that names every field (no defaults, no `..base`), so a test that fakes one service of ten spells ten.

### 2. A type parameter with a bound

```myla fragment
trait TimeSource { fun now_ms(self) -> int64 }

fun stamp<C: TimeSource>(c: C, s: str) -> str { return f"[{c.now_ms()}] {s}" }

stamp(Fixed { at: 7 }, "x")
```

Static, monomorphized, no indirect call: how `std.io`'s `Read` and `Write` and `std.compress`'s readers are injected today. The cost: every function on the way carries the type parameter, a struct that stores the service becomes generic, and it doesn't cover async methods or actors.

### 3. A type alone

A trait's function without `self` (D172) is a service chosen by a type argument, with no value passed at all:

```myla fragment
trait Greeting { fun hello() -> str }

fun greet<G: Greeting>(name: str) -> str { return G.hello() + " " + name }

greet<German>("Myla")
```

It suits stateless policies (a locale's formats, a platform's conventions, a codec). A fake that has to remember what it was called with can't be one, since a type has no state.

### Which, when

| | Record of functions | Bound | Type alone |
| --- | --- | --- | --- |
| Async, actors | yes | no | no |
| State in the provider | yes (captured) | yes | no |
| Changes signatures on the way | one parameter | a type parameter and a parameter | a type parameter |
| Cost of a call | indirect | direct, inlined | direct, inlined |
| Best for | Application services, anything faked in tests | Hot paths, streams | Policies |

## In the GUI

- **Services stay out of the model.** A model that holds a function can't be compared or saved: `#derive(Eq)` on a struct with a function field is `field 'now' has type '() -> int32', which is not Eq`. Tests, undo and record-and-replay ([[Project/GUI-plan/Testing-and-automation]]) all want the model to be plain data. (The probe on [[Project/GUI-plan/Concurrency]] keeps an actor handle in the model; this is why it shouldn't.)
- **So the dependencies are a third thing**, beside the model and the message: `ui.run(model, deps)`, and `update(var self, msg: M, cx: Context<M, D>)`, where `cx.deps` is the program's `Deps` and `cx.send`, `cx.sender` are what `ui` was. Jobs capture the services they need from it.
- **A test's app is the same model with other dependencies**: `ui.test(model, fake_deps())`. This is what "effects are swapped at the edge" on the testing page means, made part of the API.
- **Values that flow down the view tree** (theme, locale, text size) are SwiftUI's `@Environment`. The framework's own are a fixed struct. A program's own, keyed by type as in SwiftUI (`.environment(session)`, read anywhere below), need type-erased storage ([[Project/GUI-plan/Gaps#l1-type-erased-storage]]); until then they travel in `D` or as parameters of the program's view functions.

## What the language could add

### A. Context parameters

The one that fits Myla: dependencies stay parameters, the compiler does the passing. A parameter marked `using` is filled at a call from a binding of the same name and type in the caller's scope: the caller's own `using` parameter, or a `using let`.

```myla fragment
async fun fetch_and_save(url: str, using http: Http, using store: Store, using clock: Clock) -> Result<str, str> {
    let body = (await http.get(url))?
    let n = await store.save(body)
    return Ok(f"{n} saved at {clock.now_ms()}: {body}")
}

async fun refresh(urls: [str], using http: Http, using store: Store, using clock: Clock) {
    for u in urls {
        let r = await fetch_and_save(u)          // http, store and clock are passed along
    }
}

#main
async fun main() {
    using let http = real_http()
    using let store = store_of(Notes { items: [] })
    using let clock = system_clock()
    await refresh(["https://example.org"])
}

#test
async fun saves_what_it_fetched() {
    using let http = fake_http()
    using let store = store_of(Notes { items: [] })
    using let clock = fixed_clock(1000)
    expect(await fetch_and_save("ok") == Ok("1 saved at 1000: hello"))
}
```

- **It is a default argument whose default is the caller's binding.** The checker fills it where it fills defaults today (`fill_in`), so the interpreter and the backends see ordinary calls. No run-time lookup, no global, no hidden state: `myla check` says at the call which service is missing (`'fetch_and_save' uses 'clock: Clock', and nothing here provides it`).
- **Matched by name and type**, not by type alone as Scala's implicits are: two clocks can coexist, and what is passed can be read off the source.
- **Explicit in the signature.** A function's dependencies are its `using` parameters; a function between provider and user must list them too. That is the same colouring `async` has, and the same honesty. One `using deps: Deps` keeps it to one word per function.
- **An explicit argument still works**: `fetch_and_save("ok", http: other)` with named arguments (tier 1a of [[Project/GUI-plan/Syntax-with-grammar-change]]), which this feature should follow.
- **Closures and tasks** capture the bindings they use when they are made, as any variable; a function value has no `using` parameters, as it has no defaults.
- **`using`** would be a soft keyword in two places: before a parameter and before `let`.

What it gives beyond the GUI: a logger, a clock, a random source, a configuration, a request's context in a server (`using req: Request`), a transaction, a cancellation token, a locale, without threading them by hand and without a global.

### B. Module replacement in tests

Zero language cost: the loader already takes another file for a module per target (`for_target`, D223). The same seam for tests, `myla test --replace std.time=tests/fakes/time.my` or a `[test.replace]` table in `myla.toml`, swaps a whole module for a fake with the same `pub` functions (the platform interface test shows how to hold two modules to the same functions). It reaches code that calls `time.now_ms()` directly, std's own included, and it is coarse: one replacement for a whole test run, nothing per test or per window.

### C. Smaller helps

| Change | Helps |
| --- | --- |
| Struct field defaults or a copy-with expression (`Deps { ..real, clock: fixed }`) | A test replaces one service and keeps the rest; also on [[Project/GUI-plan/Data-bindings]] and [[Project/GUI-plan/Styling]] |
| Async methods in traits ([[MYLA-434]]) and traits for actors | Form 2 for async services; a record wouldn't have to be written beside every actor |
| A derive that writes the record for a trait or an actor (`#derive(Service)`) | The boilerplate of form 1 |
| Trait objects | A service is `any Http`; forms 1 and 2 become one |
| std's effects behind values (`time.system()`, `fs.local()`, `http.client()` as records or traits, the free functions kept as shorthands for them) | Library code can be given a clock or a file system; std's own modules become testable without a real one |

### Not proposed

- **A container** that resolves constructors by type at run time: it needs reflection and type-keyed storage, moves errors from `myla check` to start-up, and hides what a function uses.
- **Task-local or dynamic scope**: an ambient value any function can read without saying so. It is a global with a lifetime, and what D93 and the absence of globals were chosen to avoid.
- **Algebraic effects and handlers**: the general form of A (a handler is a provider found up the call stack). Far larger, and they change how control flows, not only how values are passed.

## Recommendation

1. **Now, as a convention**: records of functions gathered in one `Deps` struct, passed explicitly; documented with the test pattern above. The GUI framework takes it as `D` and keeps services out of the model.
2. **In std, gradually**: the effectful modules offer their service as a value beside their free functions, starting with what tests fake most (the clock, random, HTTP, the file system).
3. **Context parameters (A)** as a language proposal of their own, decided with named arguments, since both are filled in by the checker at the call and their syntax should agree. It is small (no new node reaches the backends) and general.
4. **Module replacement (B)** if std's own tests want it; it is independent of the rest.
