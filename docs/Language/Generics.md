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
```

- Parameter names may not shadow built-in type names (`int`, `str`, …) and may not repeat.
- Inside the body a `T` value can only be bound, copied, passed, stored, returned and matched by binding. Operators need a bound ([[Language/Methods-and-traits]]); `print(x)` on a `T` is an error.

## Type arguments

Type arguments are written only in **type positions**: `Box<int>`, `Result<str, IoError>`, `[Option<T>]` (D34). At a call or construction they are inferred:

1. Arguments are typed left to right. Once a parameter's type is fully known from earlier arguments, it is used as the expected type of the next argument, so `prepend(x, List.Nil)` works.
2. The expected type of the whole expression (an annotation, a parameter, a return type) seeds struct literals and enum variants.
3. A type parameter that nothing determines is an error ("cannot infer type parameter(s) T … add a type annotation").

There is no `f<int>(x)` call syntax: annotate the binding instead.

## Restrictions

- Generic functions can't be used as values or partially applied.
- `#main`, `#test` and `#derive` can't be applied to generic declarations.
- An `impl` on a generic type is either generic over all its parameters in order (`impl<T> Box<T>`) or not allowed (`impl Box<int>` is an error).
- Generic `impl`s on built-in types aren't supported.

## How generics run

| Backend | Strategy |
| --- | --- |
| Interpreter | Erasure: one body serves every instantiation; operators on erased values dispatch on the runtime value |
| Python native backend | A separate pass stamps out `name__T1_T2` copies of reachable functions, structs and enums, then re-checks the concrete program ([[src/myla/compiler/monomorphize.py]]) |
| Self-hosted backend | Monomorphizes during code generation with a substitution map |

The mangled names can collide when type names contain underscores ([[MYLA-9]]).
