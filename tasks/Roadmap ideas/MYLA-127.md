---
id: MYLA-127
title: Owned (consuming) parameters
type: feature
status: backlog
priority: low
labels: [language, ownership, design]
---
Parameters are borrowed: nothing in the callee drops them, so whatever the caller passes must outlive the call, and a callee that keeps an argument (stores it in a field, a list, a map) retains it while the caller later drops its own reference. An owned parameter mode, in the signature, would hand the caller's reference over: the callee drops it, or moves it where it is kept.

- Needed for guaranteed tail calls ([[MYLA-126]]): a value the caller owns can then be passed in a tail call.
- Cuts a retain and a release per value moved into a callee that keeps it (setters, constructors, builders), as Swift's `consuming` parameters do.
- Questions: chosen by the programmer (a keyword) or by the compiler per function (from whether the body keeps the parameter)? How it interacts with [[MYLA-123]] (staged arguments of `var self` calls), with [[MYLA-122]] (a borrowing `let` passed as an owned argument must be retained first), with function values and traits (the mode is part of the type), and with the interpreters, which have no reference counts.
- [ ] A decision on [[Project/Decisions]]
