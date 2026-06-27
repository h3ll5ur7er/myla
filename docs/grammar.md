# Myla Grammar — v0.0

A formal grammar for Myla v0.0. It is written in EBNF and split into two parts:

1. **Lexical grammar** — how characters become tokens (the lexer's job).
2. **Syntactic grammar** — how tokens become an AST (the parser's job).

EBNF notation used here:

```
A ::= B          definition
"x"              terminal (literal text)
A B              sequence (A then B)
A | B            alternation
( A )            grouping
A?               optional (zero or one)
A*               zero or more
A+               one or more
/* ... */        comment
```

---

## 1. Lexical grammar (tokens)

Whitespace and comments are consumed by the lexer and never reach the parser.

```
/* --- skipped between tokens --- */
whitespace   ::= (" " | "\t" | "\r" | "\n")+
line_comment ::= "//" (any-char-except-newline)*
block_comment::= "/*" (any-char)* "*/"   /* non-nesting; first "*/" closes */

/* --- token classes --- */
IDENT        ::= (letter | "_") (letter | digit | "_")*
letter       ::= "a".."z" | "A".."Z"
digit        ::= "0".."9"

INT          ::= digit+ int_suffix?
int_suffix   ::= ("i" | "u") ("8" | "16" | "32" | "64")
               /* e.g. 255u8, 123i64; bare digits default to `int` (= int32).
                  Float suffixes (f32/f64) are reserved for the future. */

STRING       ::= "\"" string_char* "\""
string_char  ::= escape | (any-char-except "\"" or "\\" or newline)
escape       ::= "\\" ("n" | "t" | "\\" | "\"")

BOOL         ::= "true" | "false"

/* keywords are matched before IDENT */
keyword      ::= "let" | "var" | "fun" | "return" | "struct" | "typealias"
               | "if" | "else" | "while" | "for" | "in"
               | "true" | "false" | "bool" | "str"
               | "int8" | "int16" | "int32" | "int64"
               | "uint8" | "uint16" | "uint32" | "uint64"

/* `int` is NOT a keyword: it is a built-in type alias for int32, lexed as an
   IDENT and resolved during type checking. */

/* operators & punctuation (longest match wins, e.g. "==" before "=") */
punct        ::= "->" | ".." | "==" | "!=" | "<=" | ">="
               | "&&" | "||"
               | "+" | "-" | "*" | "/" | "%"
               | "<" | ">" | "!" | "="
               | "(" | ")" | "{" | "}" | "[" | "]"
               | "," | ":" | "." | "#"
```

The lexer also tracks line/column for every token and emits an `EOF` token at
end of input.

---

## 2. Syntactic grammar

### 2.1 Program and declarations

```
program      ::= declaration* EOF

declaration  ::= attribute* decl_body
decl_body    ::= struct_decl
               | fun_decl
               | typealias_decl

attribute    ::= "#" IDENT attr_args? attr_outputs?
attr_args    ::= "(" arg_list? ")"
attr_outputs ::= "[" arg_list? "]"
               /* v0.0 built-ins: `#main` and `#test(inputs)[expected]`.
                  Unknown attribute names are a compile-time error. */

struct_decl  ::= "struct" IDENT "{" field_list? "}"
field_list   ::= field ("," field)* ","?
field        ::= IDENT ":" type

fun_decl     ::= "fun" IDENT "(" param_list? ")" ret_type? block
param_list   ::= param ("," param)* ","?
param        ::= IDENT ":" type
ret_type     ::= "->" type

typealias_decl ::= "typealias" IDENT "=" type

prim_type    ::= "bool" | "str"
               | "int8" | "int16" | "int32" | "int64"
               | "uint8" | "uint16" | "uint32" | "uint64"

type         ::= prim_type
               | IDENT   /* struct name, type-alias name, or `int` (alias of int32) */
```

### 2.2 Statements

```
block        ::= "{" statement* "}"

statement    ::= var_decl
               | assign_stmt
               | if_stmt
               | while_stmt
               | for_stmt
               | return_stmt
               | expr_stmt

var_decl     ::= ("let" | "var") IDENT (":" type)? "=" expression

assign_stmt  ::= lvalue "=" expression
lvalue       ::= IDENT ("." IDENT)*        /* variable or struct field */

if_stmt      ::= "if" expression block ("else" (if_stmt | block))?

while_stmt   ::= "while" expression block

for_stmt     ::= "for" IDENT "in" expression ".." expression block

return_stmt  ::= "return" expression?

expr_stmt    ::= expression            /* in v0.0, only call expressions are
                                          meaningful as statements */
```

> Statement separation is by newline. The parser treats a newline as a
> statement terminator; multiple statements may not share a line without one.

### 2.3 Expressions

Expression productions are layered to encode precedence and associativity
(lowest-precedence rule listed first; each defers to the next-tighter rule).

```
expression   ::= logic_or

logic_or     ::= logic_and ("||" logic_and)*
logic_and    ::= equality ("&&" equality)*
equality     ::= comparison (("==" | "!=") comparison)*
comparison   ::= term (("<" | "<=" | ">" | ">=") term)*
term         ::= factor (("+" | "-") factor)*
factor       ::= unary (("*" | "/" | "%") unary)*
unary        ::= ("-" | "!") unary
               | postfix
postfix      ::= primary postfix_op*
postfix_op   ::= "(" arg_list? ")"        /* call */
               | "." IDENT                /* field access */
primary      ::= INT
               | STRING
               | BOOL
               | IDENT
               | struct_lit
               | "(" expression ")"

struct_lit   ::= IDENT "{" field_init_list? "}"
field_init_list ::= field_init ("," field_init)* ","?
field_init   ::= IDENT ":" expression

arg_list     ::= expression ("," expression)*
```

### 2.4 Grammar ambiguity notes

- **`IDENT "{" ... "}"` (struct literal) vs. block start.** A `struct_lit`
  could be confused with an identifier expression immediately followed by a
  block (e.g. after `if`). v0.0 resolves this by only parsing a struct literal
  where an expression is expected and the `{` is not the start of a control-flow
  body. Practically: control-flow conditions parse expressions that stop before
  a `{`; a struct literal must therefore appear in clearly expression-only
  positions (initializers, arguments, `return`). When in doubt, wrap in `( )`.
- **`else if`** is grammar sugar handled by `if_stmt`'s recursive `else`
  alternative; no special token is needed.
- **`..` in `for`** is matched by the lexer as a single `..` token so it is not
  confused with two `.` field accesses.

### 2.5 Reserved for later versions (not in v0.0)

These appear in the roadmap but are intentionally absent from the v0.0 grammar:
algebraic data types (`enum`) + `match`, tuples and multiple return, lambdas /
closures + function types, user-defined macros, functional pipelines (`|>`,
`>>`) + `_`-placeholder partial application, operator overloading + custom
operators, traits, generics, collections (`[T]`, `[K: V]`, sets),
modules/imports, floats (`float32`/`float64` with `f32`/`f64` literal suffixes),
string interpolation, and compound-assignment / `**` sugar.

The self-hosting scoping ([self-hosting.md](self-hosting.md)) adds these
future-grammar items as well: bitwise & shift operators (`&`, `|`, `^`, `~`,
`<<`, `>>` — where `>>` doubles as function composition, resolved by operand
type, D24), numeric cast expressions (`expr "as" type`, D26), `break` /
`continue` statements, methods + `impl` blocks with a `self` / `var self`
receiver (D27), module-level `const` declarations (D28), a `char` type with
character literals (`'a'`, D25) + string indexing (`s[i]`), and `assert` /
`panic` / `unreachable` intrinsics. New keywords these will reserve include
`enum`, `match`, `impl`, `trait`, `as`, `const`, `char`, `break`, `continue`, and
`pub`. Concrete syntax and semantics are in
[future-features.md](future-features.md) §§7, 11–18.

(The `#main` and `#test` attributes ARE part of v0.0 — see the `attribute`
production above — but general user-defined macros are not.)

They will get their own grammar sections when introduced. Concrete syntax
proposals, semantics, and a suggested rollout order for all of these live in
[future-features.md](future-features.md). Note the functional-pipeline design
(`|>`, `>>`, `_`) is now an **accepted** decision (see
[roadmap.md](roadmap.md)); it is listed here only because it is not yet part of
the v0.0 surface grammar.
