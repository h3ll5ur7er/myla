# Generics

Functions, structs, enums, impls and traits may take type parameters. Generic code is checked once against opaque type parameters, then run by erasure in the interpreter and **monomorphized** (one concrete copy per instantiation) for native code (D13, [[Architecture/Monomorphization]]).

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

## Type arguments

Type arguments are written only in **type positions**: `Box<int>`, `Result<str, IoError>`, `[Option<T>]` (D34). At a call or construction they are inferred:

1. Arguments are typed left to right. Once a parameter's type is fully known from earlier arguments, it is used as the expected type of the next argument, so `prepend(x, List.Nil)` works.
   A lambda argument needs less: when its parameter's type is a function type whose parameter types are known (`(int) -> U` once `T` is `int`), the lambda takes them and its result is inferred from its body, which binds `U`. So `apply(3, (x) => x * 2)` and `opt.map((x) => x + 1)` need no annotation ([[MYLA-356]]).
2. The expected type of the whole expression (an annotation, a parameter, a return type) seeds struct literals and enum variants.
3. The branches of an `if` and the arms of a `match` used as a value are typed against each other when nothing is expected: one whose value can't say its whole type alone (`None`, `[]`, `[:]`, `Err(e)`, `Ok(x)`, a generic enum's variant that leaves a parameter out) is checked after the others, with the first one's type expected, so `let v = if n > 0 { Some(n) } else { None }` is an `Option<int>` ([[MYLA-290]]). When no branch says it (`if c { Ok(1) } else { Err("e") }`), annotate the binding.
4. A type parameter that nothing determines is an error ("cannot infer type parameter(s) T … add a type annotation").

There is no `f<int>(x)` call syntax: annotate the binding instead.

## Restrictions

- Generic functions can't be used as values or partially applied.
- `#main`, `#test` and `#derive` can't be applied to generic declarations.
- An `impl` on a generic type is either generic over all its parameters in order (`impl<T> Box<T>`) or not allowed (`impl Box<int>` is an error).
- A generic `impl` on a built-in type is for lists and maps: `impl<T> [T] { fun second(self) -> T { … } }`, `impl<K, V> [K: V]`, their type parameters bound by the receiver's type ([[MYLA-221]]).

## How generics run

| Backend | Strategy |
| --- | --- |
| Interpreter | Erasure: one body serves every instantiation; operators on erased values dispatch on the runtime value |
| Native backend | Monomorphizes during code generation with a substitution map (the retired Python backend stamped out copies in a separate pass and checked the concrete program again) |

Each instantiation gets its own name, whatever the type arguments are called ([[MYLA-9]], [[Architecture/Monomorphization]]).
