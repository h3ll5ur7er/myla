# Grammar

The syntax of Myla 1.0 in EBNF, as [[selfhost/parser.my]] accepts it. The original v0.0 grammar is in [[Archive/grammar]].

This page shows the rules of [[grammar/myla.ebnf]], the machine-readable grammar: the same rules plus annotations for the editor grammars it generates (MYLA-77, [[Architecture/Editor-tooling]]). A test compares the two, so change both together.

Notation: `"x"` or `'x'` is a terminal (no escapes: `"\"` is a backslash), `/…/` a character class in regex syntax, `A B` a sequence, `A | B` an alternative, `( … )` a group, `?` optional, `*` zero or more, `+` one or more. Names in capitals whose rules use only terminals, classes and lowercase helper rules are tokens; their helpers are token fragments. `NL` is a newline token; where a rule doesn't mention `NL`, a line break isn't allowed (see [[Language/Lexical-structure]]). The lexer makes no `NL` inside `( )` or `[ ]` (unless within a `{ }` in them) nor after a binary operator that ends a line, except `>` (D104 (3), [[MYLA-224]]); the rules show `NL` where that matters most, at the edges of bracketed lists and after operators, which is what the editor grammar follows (it doesn't see a line break before an operator inside brackets). `SEP` is a separator, a newline or a `;` (D61).

[TOC]

## Tokens

```ebnf
IDENT          = ident_start ident_char* ;   (* Unicode identifiers: D72 *)
INT            = ( digits | "0x" hexdigits | "0b" bindigits | "0o" octdigits ) int_suffix? ;
TUPLE_INDEX    = digits | "0x" hexdigits | "0b" bindigits | "0o" octdigits ;
FLOAT          = digits ( "." digits exponent? | exponent ) float_suffix? | digits float_suffix ;
CHAR           = "'" ( char_char | escape ) "'" ;
STRING         = '"' ( string_char | escape )* '"' ;
FSTRING_TEXT   = ( fstring_char | escape )+ ;
FORMAT_SPEC    = ":" spec_char* ;   (* a hole's format spec, D139 *)
COMMENT        = "//" line_char* | "/*" not_star* ( "*"+ not_star_slash not_star* )* "*"+ "/" ;
NL             = /\n/ ;

ident_start    = /[_\p{XID_Start}]/ ;
ident_char     = /\p{XID_Continue}/ ;
digit          = /[0-9]/ ;
hexdigit       = /[0-9a-fA-F]/ ;
digits         = digit ( "_"? digit )* ;
hexdigits      = hexdigit ( "_"? hexdigit )* ;
bindigits      = /[01]/ ( "_"? /[01]/ )* ;
octdigits      = /[0-7]/ ( "_"? /[0-7]/ )* ;
int_suffix     = ( "i" | "u" ) ( "8" | "16" | "32" | "64" ) ;
float_suffix   = "f32" | "f64" ;
exponent       = ( "e" | "E" ) ( "+" | "-" )? digits ;
escape         = "\" ( "n" | "t" | "r" | "0" | "\" | '"' | "'" | "u{" hexdigit+ "}" ) ;
               (* \u{…}: 1 to 6 hex digits naming a Unicode scalar value *)
char_char      = /[^'\\\n]/ ;
string_char    = /[^"\\\n]/ ;
fstring_char   = /[^"{}\\\n]/ ;
spec_char      = /[^"{}\\\n]/ ;
line_char      = /[^\n]/ ;
not_star       = /[^*]/ ;
not_star_slash = /[^*\/]/ ;
```

The lexer also checks what this grammar can't say: an integer literal fits 64 bits, a `\u{…}` escape names a Unicode scalar value, and f-string holes aren't empty.

## Declarations

```ebnf
program = SEP* ( declaration ( SEP+ declaration )* SEP* )? ;
SEP          = NL | ";" ;

declaration  = attribute* ( "pub"? item_decl | impl_decl ) | import_decl | "pub" pub_import ;
item_decl    = struct_decl | enum_decl | fun_decl | trait_decl | typealias_decl | const_decl ;

attribute    = "#" IDENT ( "(" expr_list? ")" )? ( "[" expr_list? "]" )? NL* ;
expr_list    = NL+ | NL* expression NL* ( "," NL* expression NL* )* ( "," NL* )? ;

struct_decl  = ( "struct" | "actor" ) IDENT type_params? "{" NL* ( field ( "," NL* field )* ","? NL* )? "}" ;
field        = IDENT ":" type ;

enum_decl    = "enum" IDENT type_params? "{" NL* ( variant ","? NL* )* "}" ;
variant      = IDENT ( "(" type ( "," type )* ","? ")" )? ;

fun_decl     = "async"? "fun" IDENT generics? "(" NL* ( param NL* ( "," NL* param NL* )* ( "," NL* )? )? ")" ( "->" type )? block ;
param        = IDENT ":" type ( "=" expression )? ;   (* a default: D136 *)
generics     = "<" generic ( "," generic )* ","? ">" ;
generic      = IDENT ( ":" trait_bound ( "+" trait_bound )* )? ;
trait_bound  = IDENT type_args? ;   (* a generic trait with its arguments, I: Iterator<T>: D171 *)
type_params  = "<" IDENT ( "," IDENT )* ","? ">" ;

impl_decl    = "impl" generics? ( type | named_type "for" type ) "{" SEP* ( method SEP* )* "}" ;
method       = attribute* method_head block ;
method_head  = "async"? "fun" IDENT generics? "(" NL* method_params? ")" ( "->" type )? ;
method_params = ( receiver | param ) NL* ( "," NL* param NL* )* ( "," NL* )? ;
              (* without a receiver: a trait's function, called on a type, D172 *)
receiver     = "self" | "var" "self" ;

trait_decl   = "trait" IDENT type_params? "{" SEP* ( method_head SEP* )* "}" ;

typealias_decl = "typealias" IDENT "=" type ;
const_decl   = "const" IDENT ":" type "=" expression ;

import_decl  = "import" import_path ( "as" IDENT )? | from_import ;
pub_import   = "import" import_path "as" IDENT | from_import ;
from_import  = "from" import_path "import" import_item ( "," import_item )* ","? ;
import_path  = ( "." | ".." )* path_segment ( "." path_segment )* ;
path_segment = IDENT | prim_type ;   (* a type's keyword names a module too, std.str: MYLA-320 *)
import_item  = IDENT ( "as" IDENT )? ;
```

## Types

```ebnf
type          = prim_type | named_type | "[" type "]" | "[" type ":" type "]"
              | "(" ")" | tuple_type | function_type ;   (* "()": the unit type, D138 *)
named_type    = IDENT ( "." IDENT )* type_args? ;   (* m.T: a module's type, D170 *)
type_args     = "<" type ( "," type )* ","? ">" ;
prim_type     = "bool" | "str" | "int8" | "int16" | "int32" | "int64"
              | "uint8" | "uint16" | "uint32" | "uint64" ;
tuple_type    = "(" type "," ( type ( "," type )* ","? )? ")" ;
function_type = "async"? "(" ( type ( "," type )* ","? )? ")" "->" type ;
```

## Statements

```ebnf
block       = "{" SEP* ( statement ( SEP+ statement )* SEP* )? "}" ;
statement   = var_decl | let_else | async_let | if_stmt | while_stmt | for_stmt | return_stmt | become_stmt
            | "break" | "continue" | defer_stmt | assignment | expression ;

var_decl    = ( "let" | "var" ) ( IDENT | bind_tuple ) ( ":" type )? "=" expression ;
async_let   = "async" "let" IDENT ( ":" type )? "=" expression ;   (* a child task, D89 *)
let_else    = "let" variant_pattern ( "|" base_pattern )* "=" expression "else" block ;   (* D137: a pattern that can fail; the else block leaves *)
bind_tuple  = "(" bind_elem "," ( bind_elem ( "," bind_elem )* ","? )? ")" ;
bind_elem   = IDENT | "(" ")" | bind_tuple ;                  (* the name "_" discards *)

if_stmt     = "if" ( cond | let_cond ) block ( NL* "else" ( if_stmt | block ) )? ;
let_cond    = "let" pattern "=" cond ;   (* if let, while let: D104 (5) *)
while_stmt  = "while" ( cond | let_cond ) block ;
for_stmt    = "for" ( IDENT | bind_tuple ) "in" cond ( ".." cond )? block ;   (* a tuple binds its parts, MYLA-390 *)
cond        = expression ;                          (* without struct literals *)
return_stmt = "return" ( expression ( "," expression )* )? ;   (* a, b is a tuple *)
become_stmt = "become" expression ;                (* a call, D87 *)
defer_stmt  = "defer" block ;                      (* runs as its block ends, D135 *)

assignment  = place ( "=" | compound_op ) expression ;
compound_op = "+=" | "-=" | "*=" | "/=" | "%=" | "&=" | "|=" | "^=" | "<<=" | ">>=" ;   (* D104 (2): place = place op expression *)
place       = ( IDENT | "self" | "(" place ")" )
              ( "." IDENT | "[" index_part "]" )* ;
```

## Expressions

```ebnf
expression  = pipe ;
pipe        = logic_or ( "|>" NL* logic_or )* ;
logic_or    = logic_and ( "||" NL* logic_and )* ;
logic_and   = equality ( "&&" NL* equality )* ;
equality    = comparison ( ( "==" | "!=" ) NL* comparison )* ;
comparison  = bit_or ( ( ( "<" | "<=" | ">=" ) NL* | ">" ) bit_or )* ;
bit_or      = bit_xor ( "|" NL* bit_xor )* ;
bit_xor     = bit_and ( "^" NL* bit_and )* ;
bit_and     = shift ( "&" NL* shift )* ;
shift       = term ( ( "<<" NL* | ">>" ) term )* ;   (* two touching "<" or ">" *)
term        = factor ( ( "+" | "-" ) NL* factor )* ;
factor      = cast ( ( "*" | "/" | "%" ) NL* cast )* ;
cast        = unary ( "as" type )* ;
unary       = ( "-" | "!" | "~" ) unary | "await" unary
            | postfix | lambda ;
              (* the parser also lets a suffix follow a lambda whose body
                 can't take it, as in (x) => x as T [0]; write ((x) => …)[0] *)
postfix     = primary ( "(" call_args? ")" | "[" NL* index_part NL* "]"
                      | "." member | "?" )* ;
member      = IDENT | TUPLE_INDEX | generic_call ;
call_args   = NL+ | NL* call_arg NL* ( "," NL* call_arg NL* )* ( "," NL* )? ;
call_arg    = "_" | expression ;            (* "_" alone: a partial-application hole *)
index_part  = bound | bound? ":" bound? ( ":" expression? )? ;   (* D142 *)
bound       = "^" expression | expression ;   (* "^n": the n-th from the end *)

primary     = INT | FLOAT | CHAR | STRING | fstring | "true" | "false"
            | "self" | IDENT | generic_call | struct_literal | "(" NL* expression NL* ")"
            | "(" NL* ")" | tuple | list | map | match_expr | if_expr
            | prim_type "." member ;   (* "()": the unit value, D138; int64.zero(): a type's function, D172 *)
generic_call = IDENT type_args "(" call_args? ")" ;
              (* f<T>(…), m.f<T>(…), x.method<T>(…) (D169): after a name, the
                 parser tries "<" as type arguments, kept when they close and
                 "(" follows, else "<" compares *)
fstring     = 'f"' ( FSTRING_TEXT | "{{" | "}}"
                   | "{" expression FORMAT_SPEC? "}" )* '"' ;
              (* lowered by the lexer to: format(STRING, expression, …) *)
if_expr     = "if" ( cond | let_cond ) block NL* "else" ( if_expr | block ) ;   (* an if used as a value, D104 (1) *)
struct_literal = IDENT "{" NL* ( field_init ( "," NL* field_init )* ","? NL* )? "}" ;
field_init  = IDENT ":" expression ;
tuple       = "(" NL* expression NL* "," NL* ( expression NL* ( "," NL* expression NL* )* ( "," NL* )? )? ")" ;
lambda      = "async"? "(" NL* ( lambda_param NL* ( "," NL* lambda_param NL* )* ( "," NL* )? )? ")" "=>" ( block | expression ) ;
lambda_param = IDENT ( ":" type )? ;
list        = "[" NL* ( expression NL* ( "," NL* expression NL* )* ( "," NL* )? )? "]" ;
map         = "[" NL* ":" "]"
            | "[" NL* map_entry NL* ( "," NL* map_entry NL* )* ( "," NL* )? "]" ;
map_entry   = expression ":" expression ;

match_expr  = "match" cond "{" NL* ( block_arm ARM_SEP? | expr_arm ARM_SEP )*
              ( block_arm ARM_SEP? | expr_arm ARM_SEP? ) "}" ;
ARM_SEP     = "," NL* | NL+ ;
block_arm   = pattern ( "if" guard )? "=>" block ;
expr_arm    = pattern ( "if" guard )? "=>" expression ;
guard       = expression ;                          (* without struct literals *)
```

## Patterns

```ebnf
pattern       = base_pattern ( "|" base_pattern )* ;
base_pattern  = INT | CHAR | STRING | "true" | "false" | "-" INT
              | "_" | IDENT | variant_pattern | "(" ")" | tuple_pattern | struct_pattern ;
variant_pattern = IDENT "." IDENT payload? | "." IDENT payload? | IDENT payload ;
payload       = "(" ( pattern ( "," pattern )* ","? )? ")" ;
tuple_pattern = "(" pattern "," ( pattern ( "," pattern )* ","? )? ")" ;
struct_pattern = IDENT "{" NL* ( field_pattern ( "," NL* field_pattern )* ","? NL* )? "}" ;
field_pattern = IDENT ( ":" pattern )? ;
```

## Ambiguities and how they are resolved

- **Struct literal or block.** In `if`, `while`, `for` and `match` heads and in match guards struct literals are off, so `{` starts the body. Parentheses turn them back on, and so does a lambda's body. The tree-sitter grammar keeps both readings until one fails (a declared conflict).
- **Parenthesis.** `( … ) =>` is a lambda (decided by scanning to the matching `)`), `(e)` is grouping, `(e,)` and `(a, b)` are tuples. In types, `(…) -> R` is a function type and `(T,)` a tuple.
- **`<`.** In types it opens type arguments; in expressions it is a comparison, except after a name, a module's member or a method's name, where the parser tries it as a call's type arguments (D169, C#'s and Swift's rule): it keeps them when they parse as types, close with `>` and a `(` follows right away, and otherwise goes back and reads a comparison, keeping no error from the attempt. So `mk<int>()`, `m.f<A, B>(x)` and `xs.mapped<str>(f)` are calls, while `a < b`, `a < b > c` and `f(a < b, c > d)` are comparisons. Two cases read differently from before: `a < b > (c)` is a call of `a` (as a comparison it was never well typed, since a `bool` isn't ordered), and so is `f(a < b, c > (d))`, one argument: write `f(a < b, c > d)` or `f((a < b), c > (d))` for two comparisons. The tree-sitter grammar keeps both readings until one fails (a declared conflict). After a cast's type a `<` opens type arguments: `a as T < b` is a parse error.
- **`>>`.** Two touching `>` are a shift in expressions and two closers in types, as in a bound's type arguments at the end of a list of type parameters (`fun total<I: Iterator<int>>(it: I)`, D171).
- **Nesting.** Expressions, types, blocks and patterns nest at most 256 levels deep (`MAX_NESTING` in the parser): deeper is a parse error, `expression nested too deeply` (or `type`, `block`, `pattern`), at the token where it goes past, not a crash of the parser or the language server ([[MYLA-182]]).
- **`|`.** Bitwise or in expressions, alternative in patterns.
- **`.`.** `t.0` is a tuple index (a `.` followed by an integer token), `x.f` a field, `E.V` a variant, `m.f` a module member (resolved by the loader); in a type, `m.T` is a module's type (D170, resolved by the loader too). `P.f(…)` on a type, `T.f(…)` on a type parameter, is a trait's function without `self` (D172, resolved by the checker: a local of the name is a value first); a type keyword before `.` is the type's name, so `int64.zero()` is one, though `int64` alone is no expression. A generic type's is called on its name alone: `Box<int>.zero()` reads as a comparison, and a `<` after a name whose type arguments close with `>` right before a `.` is a parse error saying so.
- **Greedy bodies.** A lambda's expression body, like every operand, extends as far as it can: `(x) => x + 1 |> f` is a lambda whose body is `x + 1 |> f`.
