# Builtins, type rules and modules

Verified against `selfhost/checker.my`, `selfhost/loader.my` and `lib/std/` (November 2026). Function names in parentheses are where to re-check a row. "Builtin" means the compiler knows it; "implicit std" means a method from `std.str`, `std.char`, `std.int`, `std.list`, `std.option`, `std.map` or `std.hash`. Those modules are loaded into every program that isn't itself a module of `std`, without an import (`implicit_modules`, `load_program_opts`).

## Builtin free functions (`infer_call`, `infer_intrinsic`, `infer_format`, `infer_string_builder`)

| Call | Signature / rule |
| --- | --- |
| `print(x)` | one argument: an integer, float, `char`, `bool` or `str`, or a struct or enum with `impl Format` (or a `T: Format`). No lists, tuples, maps, `Option` or unit. Writes `x` and a newline, gives nothing |
| `format("lit {} {:>8.2}", a, b)` | `-> str`. The first argument must be a string **literal**. The number of holes must equal the number of arguments. Each argument must be printable (as for `print`) or `Format`. A spec must suit the type: `{:.2}` of an int is an error. f-strings are checked the same way ("format() cannot render …") |
| `panic(msg: str)` | never returns (a return path) |
| `unreachable()` | no arguments, never returns (a return path) |
| `assert(cond: bool)`, `assert(cond, msg: str)` | gives nothing |
| `StringBuilder()`, `StringBuilder(cap: int32)` | `-> StringBuilder` |
| `std.process.exit(code)` | not builtin (import `std.process`), but the checker treats `std$process$exit` as never returning (`is_diverging_builtin`) |
| `__name(...)` primitives | a program may call them, with a `warning[primitive]` (silence it with `#allow(primitive)` or `#allow(primitive(__poll))`). The raw-memory ones (`__load64`, `__syscall`, …) are an error outside `std` (`raw_memory_call`) |

`len push pop contains remove keys chars append append_byte append_char build` are methods only: `push(xs, v)` is the error `'push' is a method: call it as 'x.push(…)'` (`function_form`). None of the names `print assert panic unreachable len push pop contains remove keys format chars StringBuilder append append_byte append_char build` (nor `wrapping_*`) may be a top-level declaration: `cannot redefine builtin 'keys'` (`collect_globals`, `is_builtin_func`). A method may use these names, except on the receivers in the next table.

## Methods on built-in types

Compiler builtins (`builtin_method`, `infer_list_mutation`, `infer_map_builtin`, `infer_wrapping`). An impl that defines one of these on that receiver is an error: `'len' is a builtin method of 'str': an impl can't define it`.

| Receiver | Builtin methods |
| --- | --- |
| every integer type | `a.wrapping_add(b)`, `wrapping_sub(b)`, `wrapping_mul(b)` (where `b` has `a`'s type), `a.wrapping_neg()`. Each gives `a`'s type |
| `[T]` | `len() -> int32`. `push(v: T)` needs a `var` place. `pop() -> T` needs a `var` place and fails at run time on an empty list |
| `[K: V]` | `len() -> int32`, `contains(k: K) -> bool`, `keys() -> [K]`. `remove(k: K)` needs a `var` place and gives nothing |
| `str` | `len() -> int32` (bytes), `chars() -> [char]` |
| `StringBuilder` | `len() -> int32`. These need a `var` place: `append(s: str)`, `append(s, start: int32, end: int32)` (byte offsets), `append_byte(b: uint8)`, `append_char(c: char)`. `build() -> str` |
| tuple | `t.hash(h: Hasher) -> Hasher` when every element is `Hash`. A tuple has no other methods and can't take impls |

Implicit std methods (the most used). Every method, with its signature, is in [stdlib.md](stdlib.md).

| Module | Methods |
| --- | --- |
| `std.str` (`impl str`) | `find`/`rfind(s) -> Option<int>`, `find_from`, `contains(s)`, `starts_with`, `ends_with`, `count(s)`, `split(sep) -> [str]`, `splitn`, `words`, `lines`, `trim`, `trim_start`, `trim_end`, `strip_prefix`/`strip_suffix -> Option<str>`, `to_upper`, `to_lower`, `bytes() -> [uint8]`, `repeat(n)`, `pad_start(w, fill: char)`, `pad_end`, `replace(old, new)`, `replacen` |
| `std.char` (`impl char`) | `is_digit`, `is_alpha`, `is_alnum`, `is_space`, `is_upper`, `is_lower`, `to_digit(radix) -> Option<int>`, `to_upper`, `to_lower`. Free function `from_digit(d, radix)`, which needs an import |
| `std.int` (`impl int8` … `impl uint64`, one block per type) | `abs`, `signum`, `min`, `max`, `clamp`, `pow`, `gcd`, `lcm`, `div_euclid`, `rem_euclid`, `count_ones`, `leading_zeros`, `trailing_zeros`, `checked_*` (an `Option`), `wrapping_pow`, `saturating_*`, `overflowing_*`, `mulmod`, `powmod`, `modinv`. A literal takes them too: `3.pow(2)` |
| `std.list` (`impl<T> [T]`, plus bounded blocks) | `reversed`, `concat`, `extend`, `insert(i, v)`, `remove_at(i) -> T`, `swap`, `truncate`, `map<U>`, `filter`, `fold<A>(init, f)`, `reduce`, `any`, `all`, `find(pred) -> Option<T>`, `position`, `count(pred)`, `min_by`/`max_by(less)`, `flat_map`, `zip`, `enumerate -> [(int, T)]`, `chunks`, `windows`, `sort_by(less)`, `sorted_by`, `sort_by_key`, `permutations`, `combinations`, `iter() -> ListIter<T>`. With `T: Eq`: `contains(v)`, `index_of(v)`, `dedup()`. With `T: Add`: `sum(zero)`. With `T: Ord`: `sort`, `sorted`, `sort_unstable`, `is_sorted`, `lower_bound`, `upper_bound`, `binary_search -> Result<int, int>`, `next_permutation`. On `[str]`: `join(sep)`. Free function `filled(n, v)`, which needs an import |
| `std.option` | `Option<T>`: `map`, `and_then`, `or_else`, `unwrap_or`, `unwrap_or_else`, `ok_or`, `is_some`, `is_none`, `expect(msg)`. `Result<T, E>`: `map`, `map_err`, `and_then`, `unwrap_or`, `ok`, `err`, `is_ok`, `is_err`, `expect`. There is no `unwrap` |
| `std.map` (`impl<K: Eq + Hash, V> [K: V]`) | `get(k) -> Option<V>`, `get_or(k, default)`, `update(k, default, f)`, `values`, `items -> [(K, V)]`, `iter`, `merge(other)`. Free function `counts(xs)`, which needs an import |
| `std.hash` (`impl Hasher`) | `add<T: Hash>(x)`, `add_u8` … `add_u64`, `add_i8` … `add_i64`, `add_bool`, `add_char`, `add_str`, `add_bytes`, `finish() -> uint64`. It also has the `Hash` impls of the integers, `char`, `bool`, `str` and `[T: Hash]`. Free functions `new()` and `with_seed`, which need an import |

**Floats have methods** from the implicit `std.float` (D197): `abs`, `floor`, `round`, `sqrt`, `cbrt`, `pow`, `powi`, `sin` … `atan2`, `sinh`, `lerp`, `clamp`, `is_nan`, `to_bits`, `total_cmp`, … on `float64` and `float32` (see [stdlib.md](stdlib.md)). `bool` has none.

A program's own method with the name of an implicit one on the same type is `duplicate method 'trim' for type 'str'`, with a note naming the standard library's module (`duplicate_method`). A new name is fine (`impl str { fun shout(self) -> str { … } }`). The modules' `pub` functions need an import (`import std.list as list`, then `list.filled(3, 0)`).

## Prelude (`prelude_src`, `register_builtin_op_traits`)

```myla fragment
#derive(Eq, Hash)
enum Option<T> { Some(T), None }
#derive(Eq, Hash)
enum Result<T, E> { Ok(T), Err(E) }
trait Format { fun format(self, spec: str) -> str }
struct Hasher { state: uint64 }           // with impl Eq; methods from std.hash
trait Hash { fun hash(self, h: Hasher) -> Hasher }
trait Iterator<T> { fun next(var self) -> Option<T> }
// built in, not redeclarable ("'Eq' is a built-in operator trait and cannot be redeclared"):
// Add<R, O>.add, Sub.sub, Mul.mul, Div.div, Rem.rem: (self, other: R) -> O   (D198)
//     a bare `Mul` is `Mul<Self, Self>`, `Mul<R>` is `Mul<R, Self>`
// Neg<O>.neg: (self) -> O                   (bare `Neg` = `Neg<Self>`: unary `-`)
// Index<I, O>.index: (self, i: I) -> O      (`x[i]`)
// IndexSet<I, V>.set_index: (var self, i: I, v: V)   (`x[i] = v`)
// Eq.eq: (self, other: Self) -> bool       Ord.cmp: (self, other: Self) -> int32
```

| Trait | What it enables |
| --- | --- |
| `Add` `Sub` `Mul` `Div` `Rem` | `+ - * / %` (and `+=` …) on the type: `Mul` both operands the type, the result too; `Mul<float>` the type times a `float`, giving the type; `Mul<V, float>` a `float` result. One impl per right operand's type, picked by the operands (`op_impls`, `find_op_impl` in checker.my). A number's impl with a struct or enum on the right gives `2.0 * v`. On `T` with that bound, by its arguments |
| `Neg` | unary `-` on a struct or enum (`Neg<O>` for another result); one per type |
| `Index` `IndexSet` | `x[i]` and `x[i] = v` (also `x[i] += v`) on a struct or enum, one impl per index type; `x` a `var` place; the element is assigned whole (not `x[i].f = v`) |
| `Eq` | `==` and `!=`, being a map key (with `Hash`), `xs.contains`/`index_of`/`dedup`, and a derived `Eq` of a type that holds it |
| `Ord` | `< <= > >=` (by `cmp`'s sign) and the sorting/searching list methods. There is no `#derive(Ord)` |
| `Hash` | being a map key (with `Eq`), `h.add(x)`, `t.hash(h)` |
| `Format` | `print(x)`, an f-string hole `{x}` / `{x:spec}`, a `format` argument. Only for structs, enums and `T: Format`: `impl Format for [int]` is accepted, but a list still can't be printed |
| `Iterator<T>` | `for x in it` (which works on a copy), `I: Iterator<T>` bounds and the `std.iter` adapters. One impl per type, so one `T` per type |

The built-in traits a primitive type has without an impl (`primitive_default_trait`):

| Type | Traits |
| --- | --- |
| integers | Add Sub Mul Div Rem Eq Ord Format Hash (and `Neg`, the signed ones) |
| floats | Add Sub Mul Div Rem Neg Eq Ord Format Hash (D196: a NaN's hash is the runtime error `cannot hash NaN`; `-0.0` hashes as `0.0`) |
| `char` | Eq Ord Format Hash |
| `bool` | Eq Format Hash (**not Ord**: `true < false` is an error) |
| `str` | Add Eq Ord Format Hash (`<` is byte-wise) |
| tuple, list | Eq and Hash when every element has it (`type_implements`). Never Ord or Format |
| `Option`, `Result` | Eq and Hash when the payload has it (derived) |
| map, function | nothing (`cannot compare values of type '[int32: int32]'`) |

Calling an operator trait's method by name on a type parameter fails: `a.eq(b)` with `T: Eq` gives `type parameter 'T' has no method 'eq': none of its bounds ('Eq') declares one (an operator trait gives its operators)`. Write `a == b`.

## `#derive` (`validate_derive_attr`, `synthesize_derives`)

Only `Eq`, `Hash`, `Json` and `Toml` can be derived, and only on a struct or enum (`cannot derive 'Ord': only 'Eq', 'Hash', 'Json' and 'Toml' are derivable`).

- `Eq`: every field or payload must be Eq. A float is Eq, a map isn't. On a generic type it gives `impl<T: Eq> Eq for Box<T>`. Deriving `Eq` and also writing `impl Eq` is an error.
- `Hash`: the type must also be `Eq` (`cannot derive Hash for 'P': it isn't Eq; derive both, '#derive(Eq, Hash)', …`). Float fields are fine (D196).
- `Json` / `Toml`: needs `import std.json as json` / `import std.toml as toml` in the file (`… std.json isn't imported`). Fields may be integers, floats, `bool`, `str`, `char`, lists, maps with `str` keys and derived types. `Option` fields are allowed (for TOML only as a struct field). No tuples.
- Attributes: `#derive(...)`, `#test(...)[...]`, a bare `#test`, `#main`, `#allow(primitive|reentrancy)`. Anything else is `unknown attribute '#x'`. `#main`/`#test` don't go on a generic function. On a method only `#test` and `#allow` are allowed.

## Type rules

**Numeric literals** (`infer_int_lit`, `infer_float_lit`, `unify`, `left_literal`, `column_step`)
- An unsuffixed integer literal takes the integer type expected there, else `int32`, and must fit: `integer literal 3000000000 does not fit in 'int32'`. A negative literal never fits an unsigned type. `-2147483648` and `-128i8` fit.
- **An integer literal never becomes a float**: `1.5 * 2` and `let x: float = 2` are errors. Write `2.0`.
- An unsuffixed float literal takes the float type expected there, else `float64`.
- In a binary operator a literal takes the other operand's type, on either side (`big + 1`, `1 + big`). In a list or map literal the literals take the type of any non-literal element (`[1, 2, big]` is `[int64]`). In a generic call a literal argument adapts only after an earlier argument fixed `T`: `max_of(big, 1)` works, `max_of(1, big)` doesn't (`T` is `int32` from the `1`; write `max_of<int64>(1, big)`).
- A char literal is a `char`, unless an integer is expected and its code is at most 127: then it has that integer type (`s[i] == 'a'`, `let b: uint8 = 'a'`, `'a' + n` with `n: int64` is an `int64`).
- Suffixes: `i8 i16 i32 i64 u8 u16 u32 u64 f32 f64`.

**`as`** (`infer_cast`): between any integer and float types, and between `char` and any integer type. Not between `char` and a float (go through an integer), and never from or to `bool`, `str` or anything else.

**Operators** (`infer_binary`, `char_arith`, `infer_overload_known`, `infer_bounded_op`)

| Operator | Operands |
| --- | --- |
| `+` | two numbers of one type, `str + str`, `char + int32 -> char`, or a type with `Add` (`Add<R, O>`: the right operand `R`, the result `O`; a number on the left by its own impl, D198) |
| `- * / %` | two numbers of one type (`%` works on floats), or a type with the trait. `char - char -> int32`, `char - int32 -> char` |
| `& \| ^`, unary `~` | integers only (`operator '&' is not defined for floats`) |
| `<< >>` | an integer on the left and any integer on the right. A constant shift amount must be in `0..width-1`. A function on the left of `>>` composes two one-argument functions |
| `== !=` | numbers, `char`, `bool`, `str`, `()`, tuples and lists of Eq elements, and Eq types (Option and Result included: `opt == None`, `m.get(k) == Some(3)`) |
| `< <= > >=` | numbers, `char`, `str`, and types with `Ord` |
| `&& \|\| !` | `bool` |

An overloaded operator's operands have the same type unless the type has an impl by type arguments for the right one (D198): with only the classic impl, `operator '+' requires both operands to have the same type, found …`; with impls by arguments, `operator '*' is not defined for 'V' and 'int32': it needs 'impl Mul<int32, …> for V'` and a note naming the impls it has.

**Map keys** (`check_key`, `key_why`): integers, `char`, `bool` and `str` (the fast path, `is_map_key`), floats (D196: hashed by std.hash's `float64.hash`, natively too, which panics `cannot hash NaN` and folds `-0.0` into `0.0`; found by `==`), or any type that is Eq and Hash: tuples and lists of such, `Option`/`Result` of such, and structs and enums with `#derive(Eq, Hash)` or both impls. A generic `K` needs `K: Eq + Hash`, even in an `impl<K, V> [K: V]` block or a function that only calls `m.len()` or `m.keys()`: write `impl<K: Eq + Hash, V> [K: V]`.

**Indexing** (`infer_index`, `check_lvalue_node`): `[T][int] -> T`, `str[int] -> uint8`, `[K: V][K] -> V` (a missing key fails at run time). Slices `a[i:j:step]` of lists and strings have the same type (a map has none). `^n` counts from the end. Strings are immutable, and you can't assign to a slice.

**`for`** (`check_for`): a list visits its elements. A map visits its **keys**: `for (k, v) in m` is an error unless the key is a tuple, so write `for (k, v) in m.items()`. A string visits its `char`s. `a..b` takes two integers, unified as in `+`. A type with `impl Iterator<T>` (or `I: Iterator<T>`) visits `T`s. A `next` method without the impl isn't enough. The loop variable can't be assigned.

**Bindings and mutation** (`check_stmt`, `check_lvalue`, `check_function`)
- `let` is immutable all the way down (`xs[0].x = 2` on a `let` is an error). Parameters are immutable, and there are no `var` parameters (`xs.push(1)` on a parameter: `push() needs a mutable list`).
- Redeclaring a name in the same scope is an error (`'x' is already declared in this scope`). An inner block may shadow it.
- `let (a, _) = t` destructures tuples only (`cannot destructure non-tuple value`).
- Everything is a value: `var b = a; b.push(2)` leaves `a` alone.
- A `var self` method needs a `var` variable, or a field or element of one, as its receiver: `cannot call the mutating method 'bump' on an immutable receiver`, or `… not a temporary` for `mk().bump()`.
- `self = v` is allowed only in a `var self` method of a built-in type (`impl int { fun double(var self) { self = self * 2 } }`) or of an enum. In a struct's method it is `cannot reassign 'self'; mutate its fields or elements instead`.
- `const NAME: T = expr`: the type is required, and the value is built from literals, other consts, arithmetic, bitwise, comparison and `as`. Consts are scalars and `str` only, not lists. There are no global variables.
- `typealias Name = Type` is transparent and takes no type parameters.

**Functions** (`check_defaults`, `call_arity`)
- Default values: `fun greet(name: str, punct: str = "!")`. Only the trailing parameters may have them, not one whose type mentions a type parameter, and not on a trait's methods. Calls may leave them out: `function 'f' expects 1 to 2 argument(s), got 3`.
- A non-generic top-level function is a value of type `(A, B) -> R` (`async (A) -> R` for an async one). A generic function or a method is not a value: `generic function 'id' cannot be used as a value`, and `xs.len` without `()` is `type '[int32]' has no fields`.
- A call of a function that gives nothing is the value `()` (`let v = f()` is fine).

**Closures** (`infer_lambda`, `check_lvalue_node`)
- `(x: int) => x + 1`, or with a block `{ … return v }`. There is no return-type annotation: the result is inferred from the body or the `return`s, which must agree.
- The parameter types may be left out only where a function type is expected (`cannot infer the type of lambda parameter 'x'; annotate it`).
- Captures are copies taken when the lambda is created. Assigning one is `a lambda can't change 'n', a variable it captures: it holds a copy of its own`.
- `f(_, 2)` partially applies, with a `_` for every open position. It doesn't work on generic or async functions. `x |> f(y)` is `f(x, y)`.

**`?`** (`infer_try`)
- On `Option<T>` in a function returning `Option<_>`, and on `Result<T, E>` in one returning `Result<_, E>` with **the same `E`** (there is no conversion: `'?' propagates an error of type 'E1', but the function returns 'Result<_, E2>'`).
- In a lambda it needs the lambda's result type to be known.
- Not allowed in `defer` or in an `async let` initializer.

**Return paths** (`block_returns`, `stmt_returns`, `match_returns`). A body with a result must contain, at its top level:
- a `return` or `become`;
- a statement call of `panic`, `unreachable` or `std.process.exit`;
- an `if … else if … else` chain that ends in `else`, with every branch returning;
- or a **`match` statement whose every arm returns or diverges** (D137).

Loops never count, `while true { return x }` included: add `unreachable()` after the loop. Otherwise you get `function 'f' may finish without returning a 'int32'` (and `lambda may finish …` for a lambda).

**`match`** (`check_exhaustive`, `check_redundant`, `check_pattern_node`)
- Exhaustiveness is checked over enums (missing variants are named), `bool`, tuples, structs and nested patterns. Integers, `char` and `str` need a `_` arm. Guarded arms don't count.
- A redundant arm is an **error**, in one of three forms: `unreachable match arm (a previous arm already matches everything)`, `(its variant(s) are already covered)` or `(earlier arms already cover it)`.
- Literal patterns are integers, `char`, `bool` and `str` only (no float patterns).
- A struct pattern may list only some fields (`P { x: 1 }`); the rest are ignored.
- The alternatives of an or-pattern must bind the same names with the same types.
- **A bare name in a pattern** that is a payload-less variant of the scrutinee's enum matches that variant (`Red => …`). Any other bare name binds anything, so a misspelt `Gren =>` catches all values silently.
- In patterns a variant may be bare (`Circle(_, r)`) or qualified by its own enum (`C.Red`), and that works for an enum reached through `import m as m` too. In expressions only `Some`, `None`, `Ok` and `Err` may be bare.
- `if let` and `while let` need a refutable pattern (`the pattern of this 'if let' always matches: use 'let' instead`).
- `let P = e else { … }` (let-else): the `else` must leave the block, with `return`, `become`, `break`, `continue`, `panic` or `unreachable`.

**Generics and inference** (`infer_generic_call`, `infer_type_args`, `explicit_subst`, `solve_bounds`, `check_call_bounds`)
- Type parameters are solved from the arguments left to right, then from the expected type (`let a: [int] = empty()`), then by explicit arguments (`empty<str>()`, `xs.map<str>(f)`, a method naming only its own type parameters).
- If none of these solves them: `cannot infer type parameter(s) T for 'f' from the arguments; add a type annotation to guide inference`.
- A generic variant or `None` without context: `cannot infer type argument(s) for 'None'; annotate the binding`.
- Inside a literal list, `[None, Some(2)]` and `[Either.Left(1), Either.Right("a")]` work, because later elements fix the open parameters.
- Bounds: `T: A + B`. A generic trait needs its arguments (`I: Iterator<T>`; a bare `I: Iterator` is an error).
  - Operators on `T` need the operator trait (`operator '>' on a value of type parameter 'T' requires the bound 'T: Ord'`).
  - Methods on `T` come only from user or prelude traits that declare them (Format, Hash, Iterator or your own).
  - A trait's functions without `self` are called on the type: `T.zero()`, `int.zero()`, `Box.zero()` (never `Box<int>.zero()`; the arguments come from the expected type).
- A type parameter can't take type arguments, can't be named after a built-in type (`int`, `str`, …), and must not repeat.
- `Self` is valid only inside a `trait` declaration. In an impl, write the type: `'Self' is only valid inside a trait declaration`.

**Impls** (`resolve_impl`, `check_impl_target`, `check_trait_conformance`)
- An impl can target a struct, an enum, an actor, or a built-in value type: an integer, float, `bool`, `char`, `str`, `StringBuilder`, a list or a map.
- It can't target a tuple or a function type (`cannot 'impl' on type '(int32, int32)'`). Generic impls on built-in types are allowed only for lists and maps.
- `impl int` is `int32` only.
- `impl<T> Box<T>` must use the type parameters in order. `impl Box<int>` is an error: `cannot 'impl' on a concrete generic instantiation`.
- All impls of a list share one method table (`[T]`), and so do all impls of a map. So `impl [int] { fun total }` makes `total` exist for `[str]` too, but calling it there is an error (`method 'total' is for '[int32]', not '[str]'`), and `impl [str] { fun total }` beside it is a duplicate.
- An inherent impl can't have a function without `self` (`function 'new' in 'impl P' has no 'self': only a trait's functions go without one`).
- A trait's methods become methods of the type: two traits with a method of the same name, or an inherent method of a trait method's name, on one type are a `duplicate method`.
- There is at most one impl per trait and type (`duplicate impl of trait …`), but an operator trait has one per right operand's (or index's) type (`duplicate impl of trait 'Mul<float64, …>' for type 'V'`). Such an impl's right operand can't use the impl's type parameters (the classic `impl<T> Mul for B<T>` excepted), an impl on a number needs a struct or enum on the right, and `Neg`/`Index`/`IndexSet` are for structs and enums. Its method is renamed `mul$float64` (`op_method_name`), so it's reached by the operator only.
- Conformance requires all of the trait's methods and no others, the same receivers (`self` / `var self` / none), and exactly the trait's signature with `Self` replaced: `does not match the trait signature (expected '(P) -> P')`.
- A trait has signatures only (no default bodies, no default values, no async methods). An actor can't implement a trait.
- You may add an inherent impl to a type imported from another module.
- A method may share a field's name (`c.keys` is the field, `c.keys()` the method), unless the field holds a function.

## Modules (`loader.my`: `resolve`, `descend`, `build_exports`, `build_bindings`, `Renamer.module_type`, `module_access`)

| Form | Binds |
| --- | --- |
| `from std.io import println, eprintln` | the names (a trailing comma is fine). `from m import f as g` renames one |
| `import std.task as task` | `task`, for `task.f(x)`, `task.T` in types and bounds, `task.E.V` in expressions |
| `import std.deque` | the whole path, `std.deque.Deque<int>` and `std.deque.new()` |
| `from .x import f`, `import .x as x` | relative to the importing file's directory. Each extra dot (`..x`) goes up one level |
| `pub from .impl import f`, `pub import .geo as geo` | re-exports. A `pub import` needs `as`. Re-exported modules chain: `u.geo.Pt`, `u.geo.origin()` |

- **Resolution.** `a.b.c` is the file `a/b/c.my` or the package root `a/b/c/c.my`; both existing is `ambiguous import`. A path without dots is looked up in the project root (the entry file's directory, or the `myla.toml` root), then the standard library root. `std.*` is looked up only in the std root, and a `--package` name only in that package's directory, which no project file or directory may shadow. The std root is the embedded copy, `<myla>/std/…`, unless `--stdlib dir` or `MYLA_STDLIB` names one (`stdroot.my`). Errors: `cannot resolve import 'x'`, `cannot read module …`.
- **Visibility.** `pub` goes on `fun`, `struct`, `enum`, `trait`, `const` and `typealias`, not on an `impl` (a parse error) and not on fields. A public struct's fields and every impl's methods are visible wherever the type is. Importing a private name gives `module 'm' does not export 'f' (declarations are private unless marked 'pub')`.
- **What `m.x` can and can't do.**
  - In a type, `m.T` must be a type and, in a bound or an impl head, a trait (`'m.f' is a function of module 'm', not a type`).
  - A struct literal or struct pattern can't be written `m.T { … }` (a parse error): import the struct with `from m import T`.
  - A module is not a value (`module 'u' cannot be used as a value — access a member with 'u.<name>'`) and not a type (`'u' is a module, not a type: name one of its types, 'u.T'`).
- **Collisions.** An import that binds a name the module already declares or imports differently is `import of 'twice' collides with an existing name in this module — rename with 'as'` (importing the same thing twice is fine). Local variables and type parameters shadow module-level names.
- **Duplicates.** Two top-level declarations with one name in a file: `duplicate top-level declaration 'x'`.
- **Mangled names.** Names from other modules are mangled to `std$io$println`. Messages show them unmangled, as `io.println`, by the module's last segment (`unmangled_in`).
- **Implicit modules** (`implicit_modules`, `merge_order`, `parse_module`):
  - The implicit modules are `std.str`, `std.char`, `std.int`, `std.float`, `std.list`, `std.option`, `std.map` and `std.hash`. They are loaded for every entry file that isn't under a `std` directory, bind no name, and are merged first, so that the program's method is the duplicate.
  - Their function bodies, and those of every other `std` module but `std.rt`, are parsed and checked only when something calls them. A type error inside an uncalled std function never shows.
  - Only the entry file's `#test` cases are parsed.

## Checker messages you will meet (exact text, then what to do)

| Message | Meaning / fix |
| --- | --- |
| `unknown name 'x'` / `unknown function 'f'` / `unknown type 'T'` (plus `help: did you mean 'y'?`) | typo, or a name from a module you haven't imported. For `get(m, k)` the help says `a map's lookup is the method 'm.get(k)'` |
| `type mismatch: 'int64' vs 'int32' (no implicit conversion between numeric types)` | mixed variables, or an int literal next to a float: cast with `as` or fix a literal |
| `cannot assign value of type 'A' to binding of type 'B'` / `cannot assign 'A' to 'B'` | `let`/`var` with an annotation, or a plain assignment |
| `argument type mismatch in call to 'f': expected 'A', found 'B'`, `function 'f' expects N argument(s), got M` | calls (also `variant 'E.V' expects …`, `method 'm' expects …`) |
| `return type mismatch: expected 'A', found 'B'`, `expected a return value of type 'A'`, `cannot return a value from a function with no return type` | return statements |
| `function 'f' may finish without returning a 'T'` | add `return`, or `unreachable()` after a loop (see Return paths) |
| `cannot assign to an immutable binding (declare it with 'var')` | also for a field or element of a `let`, and for a parameter |
| `push() needs a mutable list (declare it with 'var')`, `cannot call the mutating method 'm' on an immutable receiver (declare it with 'var')` | copy the value into a `var` first |
| `'x' is already declared in this scope` | no shadowing in the same block |
| `if condition must be 'bool', found 'int32'` (also `while condition`, `match guard`, `operand of '!'`) | no truthiness |
| `operator '+' requires numeric or string operands`, `cannot concatenate 'str' with 'int32'` | use an f-string |
| `operator '==' is not defined for 'P': it needs 'impl Eq for P' (or '#derive(Eq)')` | add `#derive(Eq)` |
| `cannot compare values of type '[int32: int32]'`, `comparison requires numeric or char operands` | maps can't be compared; tuples, lists and `bool` can't be ordered |
| `map key type must be Eq and Hash, found 'K': …` | derive both, or add `K: Eq + Hash` |
| `print() cannot print a value of type '[int32]'`, `format() cannot render a value of type 'Option<int32>'` | lists, tuples and options have no text form: build one, or `impl Format` on a struct |
| `non-exhaustive match on 'C': missing variant(s) B (add them or a '_' arm)`, `non-exhaustive match on 'int32': add a '_' arm` | |
| `unreachable match arm (…)` | delete the arm or reorder the arms |
| ``cannot infer the element type of an empty list `[]`; annotate it (e.g. `: [int]`)`` (likewise `[:]`) | `let xs: [int] = []` |
| `cannot infer type parameter(s) T …`, `cannot infer type argument(s) for 'None'; annotate the binding` | annotate, or add `f<T>(…)` |
| `'?' on a Result requires the enclosing function to return a Result`, `'?' propagates an error of type …` | match and convert by hand |
| `'push' is a method: call it as 'x.push(…)'`, `cannot redefine builtin 'build'` | builtins are methods, and their names are reserved at top level |
| `duplicate method 'trim' for type 'str'` + note `first defined in std.str, which every program sees` | rename your method |
| `function 'new' in 'impl P' has no 'self': only a trait's functions go without one` | write a free `fun new_p() -> P` |
| `'Self' is only valid inside a trait declaration` | name the type in impls |
| `operator '*' is not defined for 'V' and 'int32': it needs 'impl Mul<int32, …> for V'` | no impl for that right operand; an integer literal never becomes a float, write `2.0` |
| `unary '-' is not defined for 'V': it needs 'impl Neg for V'`, `type 'V' can't be indexed: it needs 'impl Index<int32, …> for V'`, `cannot assign to an index of 'V': it needs 'impl IndexSet<int32, float64> for V'` | implement the operator trait (D198) |
| `operator '*' on a value of type parameter 'T' is not defined for 'int32': its bounds give 'T: Mul<float64>'` | the bound's right operand decides |
| `a lambda can't change 'n', a variable it captures: it holds a copy of its own` | return the new value, or use an actor |
| `cannot infer the type of lambda parameter 'x'; annotate it (e.g. 'x: int')` | |
| `type parameter 'T' has no method 'm': it has no bounds …` / `… requires the bound 'T: Ord'` | add the bound |
| `type 'X' does not satisfy the bound 'T: Ord' required by 'f'` | implement the trait for `X` |
| `impl of trait 'Tr' for 'P' is missing method(s): a, b` / `declares method(s) not in the trait` / `does not match the trait signature (expected '(P) -> P')` | |
| `a loop over the map '[str: int32]' visits its keys, of type 'str', not its entries` | `for (k, v) in m.items()` |
| `module 'm' does not export 'f' (declarations are private unless marked 'pub')`, `import of 'x' collides with an existing name in this module — rename with 'as'`, `cannot resolve import 'x'` | module errors (`module error:` prefix) |
| `imports need the module loader: this file was type-checked on its own` | only from internal tools that check without the loader. `myla check` uses the loader |

Up to 20 errors are reported (`MAX_ERRORS`), one per function body. A declaration that fails to resolve is dropped quietly, so no follow-on errors appear (`poisoned`). Warnings (`warning[primitive]`, `warning[reentrancy]`) don't fail a check.

## Checked examples

```myla
trait Zero {
    fun zero() -> Self
}

impl Zero for int {
    fun zero() -> int { return 0 }
}

#derive(Eq, Hash)
struct Money {
    cents: int64,
}

impl Zero for Money {
    fun zero() -> Money { return Money { cents: 0 } }
}

impl Add for Money {
    fun add(self, other: Money) -> Money { return Money { cents: self.cents + other.cents } }
}

impl Format for Money {
    fun format(self, spec: str) -> str { return f"${self.cents / 100}.{self.cents % 100}" }
}

fun total<T: Zero + Add>(xs: [T]) -> T {
    var acc = T.zero()
    for x in xs {
        acc = acc + x
    }
    return acc
}

enum Light { Red, Green }

impl Light {
    fun next(var self) {
        self = match self {
            Red => Light.Green
            Green => Light.Red
        }
    }
}

fun sign(n: int) -> str {
    match n > 0 {
        true => { return "+" }
        false => { return "-" }
    }
}

fun main() {
    print(total([1, 2, 3]))
    let m = total([Money { cents: 150 }, Money { cents: 275 }])
    print(m)
    var seen: [Money: int] = [:]
    seen[m] = 1
    var l = Light.Red
    l.next()
    print(match l { Red => "red", Green => "green" })
    let big: int64 = 5000000000
    let xs = [1, 2, big]
    print(xs[0] + 1)
    print(sign(-3))
}
// output:
// 6
// $4.25
// green
// 2
// -
```
