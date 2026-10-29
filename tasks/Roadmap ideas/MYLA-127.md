---
id: MYLA-127
title: Owned (consuming) parameters
type: feature
status: review
priority: low
labels: [language, ownership, design]
---
Parameters are borrowed: nothing in the callee drops them, so whatever the caller passes must outlive the call, and a callee that keeps an argument (stores it in a field, a list, a map) retains it while the caller later drops its own reference. An owned parameter mode, in the signature, would hand the caller's reference over: the callee drops it, or moves it where it is kept.

- Needed for guaranteed tail calls ([[MYLA-126]]): a value the caller owns can then be passed in a tail call.
- Cuts a retain and a release per value moved into a callee that keeps it (setters, constructors, builders), as Swift's `consuming` parameters do.
- Questions: chosen by the programmer (a keyword) or by the compiler per function (from whether the body keeps the parameter)? How it interacts with [[MYLA-123]] (staged arguments of `var self` calls), with [[MYLA-122]] (a borrowing `let` passed as an owned argument must be retained first), with function values and traits (the mode is part of the type), and with the interpreters, which have no reference counts.
- [x] A decision on [[Project/Decisions]]: chosen by the compiler (D86)
- [x] A last use moves (the retain and drop pair cancels), and a value something borrows keeps its reference
- [x] Owned parameters in the self-hosted backend: the callee, the callers, function values' adapters and partial applications, the verifier

## How

- **Moves** (`moves` in [[selfhost/ir.my]], run on every function after lowering, before the verifier). In a block, a `retain` of the whole value an owning slot holds (`retain T %v` of `%v = load $s`, or `retain T [%d]` right after `copy [%d], [%a]` with `%a = addr $s`) followed by the slot's `drop`, with nothing touching the slot or reading anything taken from it in between (the loaded value read once, by whoever takes it), loses the retain and the drop becomes `moved`. The only holder besides the slot is the taker, which then owns the slot's reference. `borrowed_slots` finds the owning slots that a slot owning nothing is stored or copied from (a borrowing `let`, a loop's list, a match's borrowed copy, through loads, offsets and elements): those keep their reference, since the borrower may read the value after the new owner let it go. The pass works out the borrowers only for a function with a candidate and rebuilds only the blocks it changes.
- **Choosing** (`find_kept_params` in [[selfhost/codegen.my]], before any function is lowered). One scan over every body (`scan_block`, `scan_stmt`, `scan_expr`) collects the names the body keeps as a whole value (returned; stored in a `var`, by an assignment, in a struct, tuple, list or map literal, a payload, by `push`; read by a lambda, which captures it) and every call's arguments, each a new value (a call's result, a concatenation, a list or map literal, or a variable right in a `return`) or not. A parameter (not `self`) is owned when its function keeps it and new values outnumber the others at its calls (counted by the name a call uses, so methods of one name share their vote) and, when lowered, it is a string, list, map or builder (`owned_param`, `owned_params`).
- **Callee** ([[selfhost/lower.my]]). An owned parameter's slot owns and is registered with the function's scope: every `return`, and the end of the body, drop it; `moves` turns the drop at the keeping site into a hand-over. The verifier treats it as holding a value on entry.
- **Callers.** `direct_call` hands over an owned temporary (`retain_or_take`), a staged copy of a `var self` receiver's part ([[MYLA-123]]), or retains. Lambdas' parameters stay borrowed, and calls through function values don't know their callee: `myla_<fn>__fnval` and partial-application thunks retain what they pass to an owned parameter.

## Evidence

- New tests first: `test_a_last_use_moves` (a list and a struct returned from a local without a retain; one read after it is pushed keeps its retain), `test_tail_calls_hand_over_owned_arguments` (with [[MYLA-126]]), and the parity program `borrowed_lets_survive_a_moved_value` (a `let` of a variable, and a loop over one, read after the variable's value was handed to a new owner and released), which the first version of `moves` failed (it printed an empty string) and every backend passes now.
- `moves` alone, the same source compiled before and after: 2,616.3 → 2,597.4 million instructions compiling itself (−0.7%), 2,342 → 1,932 inline retains; the pass costs about as much as it saves on the self-compile (2,587.0 → 2,591.2 million on the same input).
- Owned parameters: on the compiler only 25 parameters are owned, and the code it compiles to runs the same instructions (2,699.77 million either way), with a 0.3% larger binary; the scan of every body costs about 1.4% of the self-compile (2,661.4 → 2,699.8 million instructions on the same input; wall times within the noise: medians 0.928, 0.903 and 0.926 s without the scan, without owned parameters, and with both). A first rule (owned whenever the body keeps it) more than doubled the compiler's inline retains (1,943 → 4,726: callers retaining variables) for no fewer instructions; the census of call sites keeps owned to where it pays and makes the recursions of [[MYLA-126]] jump. The stress programs: see [[MYLA-126]].
- Unit 595, integration 2, burn 745 (5 skipped) and the extension's 54 tests pass; the bootstrap reaches its byte-identical fixed point (5,203,771 bytes).
