# Generics

Functions, structs, enums, actors, impls and traits may take type parameters. Generic code is checked once against opaque type parameters, then run in the interpreter with each call's type parameters bound to the types they stand for ([[MYLA-414]], [[Architecture/Interpreter]]) and **monomorphized** (one concrete copy per instantiation) for native code (D13, [[Architecture/Monomorphization]]).

[TOC]

## Declaring

```myla
struct Box<T> {
    value: T,
}

enum List<T> {
    Cons(T, List<T>),
    Nil,
}

fun first<A, B>(p: (A, B)) -> A {
    return p.0
}

fun len_of<T>(l: List<T>) -> int {
    return match l {
        Cons(_, rest) => 1 + len_of(rest)
        Nil => 0
    }
}

fun main() {
    let b = Box { value: "x" }
    let l: List<int> = List.Cons(1, List.Cons(2, List.Nil))
    print(first((b.value, 3)))
    print(len_of(l))
}
// output:
// x
// 2
```

- Parameter names may not shadow built-in type names (`int`, `str`, …) and may not repeat.
- Inside the body a `T` value can only be bound, copied, passed, stored, returned and matched by binding. Operators need a bound ([[Language/Methods-and-traits]]); `print(x)` on a `T` without a `Format` bound is an error.
- An actor takes them as a struct does, `actor Cell<T> { value: T }` with `impl<T> Cell<T> { … }`: an instance per type argument, each serving its own calls one at a time ([[Language/Concurrency#generic-actors]], [[MYLA-386]]).
- A bound's trait gives `T` its functions without `self` too: `T.zero()` under `T: Zero` makes a `T` with no value in hand, the function of the type `T` stands for in each call ([[Language/Methods-and-traits#functions-without-self]], D172).

## Type arguments

Type arguments are written in **type positions**: `Box<int>`, `Result<str, IoError>`, `[Option<T>]` (D34). A call of a generic function or method may name them too, `mk<int>()` ([explicit type arguments](#explicit-type-arguments), D169); otherwise, at a call or construction they are inferred:

1. Arguments are typed left to right. Once a parameter's type is fully known from earlier arguments, it is used as the expected type of the next argument, so `prepend(x, List.Nil)` works.
   A lambda argument needs less: when its parameter's type is a function type whose parameter types are known (`(int) -> U` once `T` is `int`), the lambda takes them and its result is inferred from its body, which binds `U`. So `apply(3, (x) => x * 2)` and `opt.map((x) => x + 1)` need no annotation ([[MYLA-356]]).
   A bound naming a generic trait with its arguments, `I: Iterator<T>`, fixes them once its parameter is known: the type an argument gives `I` has one impl of `Iterator` (D55), whose argument is `T` ([[Language/Methods-and-traits#bounds]], D171). So `fun count<I: Iterator<T>, T>(it: I) -> int` needs nothing else, and in `map(it, (x) => x * 3)` the lambda's `x` is the iterator's `T`. Native code solves the instance's `T` the same way.
2. The expected type of the whole expression (an annotation, a parameter, a return type, a field, a list's element) seeds struct literals and enum variants, and fixes the type parameters of a generic function's or method's call that its arguments leave open ([[MYLA-315]]): `let d: Deque<int> = deque.new()`, `return mk()` in a function that returns `B<str>`, `f(mk())` where `f` takes a `B<int>`, `Graph { todo: deque.new() }`. What the arguments fix comes first; the expected type only fills the rest, and hints the arguments whose parameter's type the earlier ones leave open, so `let b: B<int64> = of([5000000000])` makes the list an `[int64]`. An expected type that doesn't fit the result is not an error here: the call's type is compared where it is used.
   Inside generic code a type parameter of the enclosing function is a known type, so the return type `B<T>` gives the field `items: [T]` of `B { items: [] }` its type, as it does an empty map `[:]` or `None`.
3. The branches of an `if` and the arms of a `match` used as a value are typed against each other when nothing is expected: one whose value can't say its whole type alone (`None`, `[]`, `[:]`, `Err(e)`, `Ok(x)`, a generic enum's variant that leaves a parameter out) is checked after the others, with the first one's type expected, so `let v = if n > 0 { Some(n) } else { None }` is an `Option<int>` ([[MYLA-290]]). When no branch says it (`if c { Ok(1) } else { Err("e") }`), annotate the binding.
4. The elements of a list or map literal share one type, which all of them fix together when nothing is expected: an element that leaves a type parameter open (`None`, `[]`, `Err(e)`, `Either.Left(1)`) leaves it to a later element, so `[Either.Left(1), Either.Right("a")]` is an `[Either<int, str>]`, `[None, Some(2u8)]` an `[Option<uint8>]`, `[[], [1]]` an `[[int]]` and `["a": None, "b": Some(2)]` a `[str: Option<int>]`, as in Rust ([[MYLA-401]]); this holds inside nested lists, maps and tuples too (`[(None, 'a'), (Some("b"), 'c')]`). What an earlier element fixed hints the later ones, so `[Either.Left(1u8), Either.Left(2), Either.Right("x")]` makes the `2` a `uint8`. When no element fixes a parameter (`[Either.Left(1), Either.Left(2)]`), the first element that left it open reports it, as it would alone; an element of another type is a mismatch that shows the open parameter as `_` ("type mismatch: 'Option<_>' vs 'int32'").
5. A type parameter that nothing determines is an error ("cannot infer type parameter(s) T … add a type annotation"): one that neither the explicit type arguments, the arguments nor the expected type fix, such as a call statement's `mk()`, `let b = mk()`, or a parameter the result doesn't name and no bound fixes (`fun count<T>() -> int`); `mk<int>()` and `count<str>()` name it.

```myla
struct B<T> {
    items: [T],
}

impl<T> B<T> {
    fun size(self) -> int {
        return self.items.len()
    }
}

fun mk<T>() -> B<T> {
    return B { items: [] }
}

fun names() -> B<str> {
    return mk()
}

fun total(b: B<int>) -> int {
    var t = 0
    for x in b.items {
        t += x
    }
    return t
}

fun main() {
    let a: B<int> = mk()
    var n = names()
    n.items.push("x")
    print(a.size() + n.size())
    print(total(mk()))
}
// output:
// 1
// 0
```

A type parameter only a bound names, fixed by the bound:

```myla
struct Up {
    i: int,
    stop: int,
}

impl Iterator<int> for Up {
    fun next(var self) -> Option<int> {
        if self.i >= self.stop { return None }
        self.i += 1
        return Some(self.i - 1)
    }
}

// `T` is what `I`'s impl of Iterator says
fun to_list<I: Iterator<T>, T>(it: I) -> [T] {
    var out: [T] = []
    for x in it { out.push(x) }
    return out
}

fun main() {
    let xs = to_list(Up { i: 2, stop: 5 })
    print(xs.len())
    print(xs[0] + xs[2])
}
// output:
// 3
// 6
```

### Explicit type arguments

Where nothing fixes a type parameter, a call can name it: `mk<int>()`, `deque.new<str>()`, `m.f<A, B>(x)`, `xs.mapped<str>(f)` (D169, [[MYLA-373]]). They are written after the function's or method's name, before its `(`:

- They come first: the arguments and the expected type are typed with them, so `widen<int64>(5000000000)` takes an `int64`, and an argument that doesn't fit is a mismatch (`widen<str>(true)`: expected 'str', found 'bool').
- There is one for each type parameter, in the declaration's order; another count is an error naming both (`function 'mk' expects 1 type argument(s), got 2`).
- A method's name its own type parameters, not its impl's, which its receiver gives: `b.mapped<str>(f)` on a `B<int>`. A method without type parameters of its own, a function that isn't generic, a builtin or a variant takes none (`function 'twice' is not generic (it takes no type arguments)`).
- In the parser, a `<` after a name or a member is tried as type arguments and kept when they close with `>` and a `(` follows; otherwise it's a comparison, as before. So `a < b` and `f(a < b, c > d)` compare, but `f(a < b, c > (d))` is one call of `a` with the type arguments `b, c` ([[Language/Grammar#ambiguities-and-how-they-are-resolved]]). Only in a call's argument list (D186): in a list, map or tuple literal `[a < b, c > (d)]` is two comparisons, and so is `f"{a < b} {c > (a)}"`, whose holes are parsed one by one; there a generic call with two or more type arguments needs a `let` of its own (`let p = pair<int, str>(1, "a")`), and one with a single type argument, `[mk<int>()]`, is read as before.

```myla
struct B<T> {
    items: [T],
}

impl<T> B<T> {
    fun mapped<U>(self, f: (T) -> U) -> B<U> {
        var out: [U] = []
        for x in self.items {
            out.push(f(x))
        }
        return B { items: out }
    }
}

fun mk<T>() -> B<T> {
    return B { items: [] }
}

fun main() {
    var d = mk<str>()
    d.items.push("x")
    print(d.items.len())
    let b = B { items: [1, 2] }
    print(b.mapped<str>((x) => f"#{x}").items[1])
    let x = 1
    print(x < 2)
}
// output:
// 1
// #2
// true
```

## Restrictions

- Generic functions can't be used as values or partially applied.
- `#main` and `#test` can't be applied to generic declarations. `#derive` can ([[MYLA-379]]): the impl it writes is bounded by the trait on every type parameter, `impl<T: Eq> Eq for Box<T>` ([[Language/Methods-and-traits]]).
- An `impl` on a generic type (a struct, enum or actor) is either generic over all its parameters in order (`impl<T> Box<T>`) or not allowed (`impl Box<int>` is an error).
- A struct's or actor's own type parameters take no bounds (`struct S<T: Add>` is a parse error): the impl that needs one says it, `impl<T: Add> S<T>`.
- A generic `impl` on a built-in type is for lists and maps: `impl<T> [T] { fun second(self) -> T { … } }`, `impl<K: Eq + Hash, V> [K: V]` (a key needs its bound written, D167), their type parameters bound by the receiver's type ([[MYLA-221]]).

## How generics run

| Backend | Strategy |
| --- | --- |
| Interpreter | Erasure: one body serves every instantiation. Each generic call binds the callee's type parameters to the types the checker solved there (D172, [[MYLA-414]]), so arithmetic, comparisons and formatting typed by a type parameter behave as for the concrete type: an `int8` sum overflows (D175), a `uint64` compares and prints unsigned, a `float32` rounds; a trait's function on a type parameter (`T.zero()`) and a method on a value of type-parameter type find their type there |
| Native backend | Monomorphizes during code generation with a substitution map (the retired Python backend stamped out copies in a separate pass and checked the concrete program again) |

Each instantiation gets its own name, whatever the type arguments are called ([[MYLA-9]], [[Architecture/Monomorphization]]).

Polymorphic recursion, a generic function calling itself with a larger type (`grow<T>` calling `grow<[T]>`), runs in the interpreter, but native code would need an instance for every size: `myla build` refuses the call, `the instances of 'grow' nest without end: this call asks for one whose type arguments are 65 types deep (the limit is 64)`, as a type error ([[MYLA-415]]). A finite type past the limit that a program writes, `id(x)` of a list 65 deep, is refused the same way, in its own words: `the instance of 'id' this call asks for is too large to build: its type arguments are 65 types deep (the limit is 64)` ([[MYLA-543]]); `myla check` doesn't apply the limit. The operators of a generic impl (`impl<T: Add> Add for Box<T>`) call its instance for the operands' types, as its methods do.
