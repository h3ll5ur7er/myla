# std.algebra

The traits of a type's distinguished values (D201, [[MYLA-587]]): `Zero` (`fun zero() -> Self`, the additive identity), `One` (`fun one() -> Self`, the multiplicative one; a vector's all ones) and `Identity` (`fun identity() -> Self`, what `*` leaves unchanged for a matrix or a rotation). They are functions without `self` (D172), called on a type, `int.zero()`, `Vec3.zero()`, `Mat4.identity()`, or on a type parameter bounded by the trait, `T.zero()`. Every integer and float type implements `Zero` and `One` here; [[Language/Standard-library/Vector]], [[Language/Standard-library/Matrix]] and [[Language/Standard-library/Quaternion]] implement them for theirs. `sum(xs)` and `product(xs)` fold a list from `T.zero()` and `T.one()`.

```myla
import std.algebra as algebra
from std.algebra import Zero

fun total<T: Add + Zero>(xs: [T]) -> T {
    var acc = T.zero()
    for x in xs {
        acc = acc + x
    }
    return acc
}

fun main() {
    print(total([1, 2, 3]))
    print(total([0.5, 0.25]))
    print(algebra.product([2.0, 3.0, 4.0]))
    print(uint8.one())
}
// output:
// 6
// 0.75
// 24
// 1
```

A program that imports this module, or one of the three above, can't also give a number type a `zero` or `one` method of its own: the trait's is the type's method (a `duplicate method`).
