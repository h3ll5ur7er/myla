---
id: MYLA-40
title: "Rust concurrency: channels never close, actors deadlock"
type: bug
status: backlog
priority: medium
labels: [rust, concurrency]
---
- [ ] `Value::Chan` holds both ends of the channel, so it never closes: `recv()` with no sender left hangs forever
- [ ] Spawned tasks that nobody joins are killed when `main` returns, so `spawn { print(..) }` prints nothing; decide (join at exit, or document)
- [ ] An actor method holds the actor's non-reentrant `std::sync::Mutex` for its whole body, so an actor calling a method on its own handle deadlocks
- [ ] `async` on actor and impl methods is ignored; actor fields can't be read from outside ("type `C` has no field `n`")
- [ ] `Channel::bounded` exists but nothing in Myla can create a bounded channel
