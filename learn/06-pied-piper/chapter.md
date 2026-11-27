title: Pied Piper
emoji: 📈
tagline: Option, Result and the ? operator. Middle-out error handling.

Myla has no exceptions and no null. A value that may be missing is an `Option<T>`: `Some(x)` or `None`. A computation that may fail gives a `Result<T, E>`: `Ok(x)` or `Err(e)`. The checker makes you look at both cases, so nothing blows up at the demo in front of the investors.

- `match` takes them apart: `match r { Ok(v) => …, Err(e) => … }`.
- `opt.unwrap_or(d)` is the value, or `d` when there's none.
- Inside a function that returns a `Result`, `r?` is the value of an `Ok`, and returns an `Err` at once.

See [[Language/Types]] (Option and Result) and [[Language/Expressions-and-operators]] for `?`. Optimal tip-to-tip efficiency.
