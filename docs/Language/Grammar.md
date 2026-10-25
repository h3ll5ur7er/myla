# Grammar

The syntax of Myla 1.0 in EBNF, as [[src/myla/parser.py]] accepts it. The original v0.0 grammar is in [[Archive/grammar]].

Notation: `"x"` terminal, `A B` sequence, `A | B` alternative, `( … )` group, `?` optional, `*` zero or more, `+` one or more. `NL` is a newline token; where the grammar doesn't mention `NL`, newlines aren't allowed (see [[Language/Lexical-structure]] for where the parser skips them).

[TOC]

## Tokens

```ebnf
IDENT    = (letter | "_") (letter | digit | "_")* ;          (* minus keywords *)
INT      = ( digits | "0x" hexdigits | "0b" bindigits | "0o" octdigits ) int_suffix? ;
digits   = digit ( "_"? digit )* ;                          (* likewise per base *)
int_suffix   = ("i" | "u") ("8" | "16" | "32" | "64") ;
FLOAT    = digits ( "." digits )? ( ("e" | "E") ("+" | "-")? digits )? float_suffix? ;
                                (* needs a fraction, an exponent or the suffix *)
float_suffix = "f32" | "f64" ;
CHAR     = "'" ( char | "\" ( "n" | "t" | "r" | "\" | "'" | "0" ) | "\u{" hex{1,6} "}" ) "'" ;
STRING   = '"' ( char | "\" ( "n" | "t" | "\" | '"' ) )* '"' ;
FSTRING  = 'f"' ( char | escape | "{{" | "}}" | "{" expression "}" )* '"' ;
           (* lowered to: IDENT(format) "(" STRING ( "," expression )* ")" *)
```

## Declarations

```ebnf
program      = NL* ( declaration terminator )* EOF ;
terminator   = NL+ | (* before "}" or EOF *) ;

declaration  = attribute* "pub"? decl ;
decl         = struct_decl | enum_decl | fun_decl | impl_decl | trait_decl
             | typealias_decl | const_decl | import_decl ;
             (* no attributes on impl and import; no "pub" on impl *)

attribute    = "#" IDENT ( "(" expr_list? ")" )? ( "[" expr_list? "]" )? NL* ;

struct_decl  = "struct" IDENT type_params? "{" NL* ( field ( "," NL* field )* ","? )? NL* "}" ;
field        = IDENT ":" type ;

enum_decl    = "enum" IDENT type_params? "{" NL* ( variant ( ","? NL* ) )* "}" ;
variant      = IDENT ( "(" type ( "," type )* ","? ")" )? ;

fun_decl     = "fun" IDENT generics? "(" ( param ( "," param )* )? ")" ( "->" type )? block ;
param        = IDENT ":" type ;
generics     = "<" generic ( "," generic )* ">" ;
generic      = IDENT ( ":" IDENT ( "+" IDENT )* )? ;     (* bound: trait names *)
type_params  = "<" IDENT ( "," IDENT )* ">" ;             (* no bounds on structs/enums/traits *)

impl_decl    = "impl" generics? type ( "for" type )? "{" NL* ( method NL* )* "}" ;
             (* with "for": the first type is the trait, possibly with arguments *)
method       = method_head block ;
method_head  = "fun" IDENT generics? "(" receiver ( "," param )* ","? ")" ( "->" type )? ;
receiver     = "self" | "var" "self" ;

trait_decl   = "trait" IDENT type_params? "{" NL* ( method_head NL* )* "}" ;

typealias_decl = "typealias" IDENT "=" type ;
const_decl   = "const" IDENT ":" type "=" expression ;

import_decl  = "import" import_path ( "as" IDENT )?           (* "pub import" requires "as" *)
             | "from" import_path "import" import_item ( "," import_item )* ;
import_path  = ( "." | ".." )* IDENT ( "." IDENT )* ;
import_item  = IDENT ( "as" IDENT )? ;
```

## Types

```ebnf
type      = prim_type
          | IDENT ( "<" type ( "," type )* ">" )?        (* named, generic, alias, int, float, char … *)
          | "[" type "]"                                 (* list *)
          | "[" type ":" type "]"                        (* map *)
          | "(" type "," ( type ( "," type )* ","? )? ")"  (* tuple; (T,) is the 1-tuple *)
          | "(" ( type ( "," type )* ","? )? ")" "->" type ;   (* function *)
prim_type = "bool" | "str" | "int8" | "int16" | "int32" | "int64"
          | "uint8" | "uint16" | "uint32" | "uint64" ;
```

## Statements

```ebnf
block      = "{" NL* ( statement ( NL+ | (* before "}" *) ) )* "}" ;
statement  = var_decl | if_stmt | while_stmt | for_stmt | return_stmt
           | "break" | "continue" | assign_or_expr ;

var_decl   = ( "let" | "var" ) ( IDENT | bind_tuple ) ( ":" type )? "=" expression ;
bind_tuple = "(" bind_elem "," ( bind_elem ( "," bind_elem )* ","? )? ")" ;
bind_elem  = IDENT | "_" | bind_tuple ;

if_stmt    = "if" cond block ( NL* "else" ( if_stmt | block ) )? ;
while_stmt = "while" cond block ;
for_stmt   = "for" IDENT "in" cond ( ".." cond )? block ;
cond       = expression ;          (* parsed with struct literals disabled *)
return_stmt = "return" ( expression ( "," expression )* )? ;   (* a, b → tuple *)

assign_or_expr = expression ( "=" expression )? ;
                 (* the target must be IDENT, or field/index chains rooted at one *)
```

## Expressions

```ebnf
expression = pipe ;
pipe       = logic_or ( "|>" logic_or )* ;
logic_or   = logic_and ( "||" logic_and )* ;
logic_and  = equality ( "&&" equality )* ;
equality   = comparison ( ( "==" | "!=" ) comparison )* ;
comparison = bit_or ( ( "<" | "<=" | ">" | ">=" ) bit_or )* ;
bit_or     = bit_xor ( "|" bit_xor )* ;
bit_xor    = bit_and ( "^" bit_and )* ;
bit_and    = shift ( "&" shift )* ;
shift      = term ( ( "<<" | ">>" ) term )* ;     (* two adjacent "<" / ">" tokens *)
term       = factor ( ( "+" | "-" ) factor )* ;
factor     = cast ( ( "*" | "/" | "%" ) cast )* ;
cast       = unary ( "as" type )* ;
unary      = ( "-" | "!" | "~" ) unary | postfix ;
postfix    = primary ( "(" call_args? ")" | "[" expression "]"
                     | "." ( IDENT | INT ) | "?" )* ;
call_args  = NL* call_arg ( NL* "," NL* call_arg )* NL* ;
call_arg   = "_" | expression ;                    (* "_" alone: a partial-application hole *)

primary    = INT | FLOAT | CHAR | STRING | "true" | "false" | "self"
           | IDENT
           | IDENT "{" NL* ( IDENT ":" expression ( "," NL* … )* ","? )? NL* "}"   (* struct literal *)
           | "(" expression ")"
           | "(" expression "," ( expression ( "," expression )* ","? )? ")"      (* tuple *)
           | lambda
           | "[" NL* ( expression ( "," NL* expression )* ","? )? NL* "]"         (* list *)
           | "[" ":" "]" | "[" NL* expression ":" expression ( "," … )* ","? NL* "]"  (* map *)
           | match_expr ;

lambda     = "(" ( IDENT ( ":" type )? ( "," IDENT ( ":" type )? )* )? ")" "=>" ( expression | block ) ;
             (* recognised by a "=>" right after the matching ")" *)

match_expr = "match" cond "{" NL* ( arm ( "," NL* | NL+ | (* after a block body *) ) )+ "}" ;
arm        = pattern ( "if" cond )? "=>" ( block | expression ) ;
```

## Patterns

```ebnf
pattern      = base_pattern ( "|" base_pattern )* ;
base_pattern = INT | CHAR | STRING | "true" | "false" | "-" INT
             | "_" | IDENT                               (* binding, or a payload-less variant *)
             | ( IDENT "." )? IDENT "(" ( pattern ( "," pattern )* ","? )? ")"   (* variant *)
             | IDENT "." IDENT | "." IDENT ( "(" … ")" )?                          (* qualified / bare variant *)
             | "(" pattern "," ( pattern ( "," pattern )* ","? )? ")"              (* tuple *)
             | IDENT "{" NL* ( IDENT ( ":" pattern )? ( "," NL* … )* )? NL* "}" ;  (* struct *)
```

## Ambiguities and how they are resolved

- **Struct literal or block.** In `if`, `while`, `for` and `match` heads struct literals are off, so `{` starts the body. Parentheses turn them back on.
- **Parenthesis.** `( … ) =>` is a lambda (decided by scanning to the matching `)`), `(e)` is grouping, `(e,)` and `(a, b)` are tuples. In types, `(…) -> R` is a function type and `(T,)` a tuple.
- **`<`.** In types it opens type arguments; in expressions it is a comparison. Generic arguments never appear in expressions (D34).
- **`>>`.** Two touching `>` are a shift in expressions and two closers in types.
- **`|`.** Bitwise or in expressions, alternative in patterns.
- **`.`.** `t.0` is a tuple index (a `.` followed by an integer token), `x.f` a field, `E.V` a variant, `m.f` a module member (resolved by the loader).
