---
id: MYLA-386
title: "Generic actors: actor Channel<T>"
type: feature
status: backlog
priority: medium
labels: [language, concurrency, actors, generics]
---
Found by the channels lane ([[MYLA-351]]): `actor Box<T>` is refused ("an actor can't have type parameters"), so `std.task`'s `Channel<T>` can't own its queue. The lane's version makes every program declare an actor per element type and pass its method in as a closure. A first-class `task.channel<int>(4)` needs generic actors.

- [ ] `actor A<T> { … }` and `impl<T> A<T> { … }`: the checker, the interpreter, the lowering (an actor's instance per type argument), every target
- [ ] Values crossing into and out of a generic actor are deep-copied as for any actor (D89–D97)
- [ ] Parity programs and the concurrency stress tests over a generic actor
