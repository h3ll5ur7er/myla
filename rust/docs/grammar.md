# Myla (Rust edition) — Grammar

EBNF-ish grammar for the language. `{ X }` = zero or more, `[ X ]` = optional,
`|` = alternation. Terminals are in `"quotes"`. `NL` is a newline or `;`
statement terminator (see the optional-semicolon rules in
[language-spec.md §4](language-spec.md)).

## Lexical

```ebnf
ident   = letter , { letter | digit | "_" } ;
int     = ( dec | hex | bin | oct ) , [ intsuffix ] ;
dec     = digit , { digit | "_" } ;
hex     = "0x" , hexdigit , { hexdigit | "_" } ;
bin     = "0b" , ("0"|"1") , { "0" | "1" | "_" } ;
oct     = "0o" , octdigit , { octdigit | "_" } ;
intsuffix = ("i"|"u") , ("8"|"16"|"32"|"64") ;
float   = dec , "." , dec , [ exp ] , [ floatsuffix ]
        | dec , exp , [ floatsuffix ]
        | dec , floatsuffix ;
exp     = ("e"|"E") , [ "+" | "-" ] , dec ;
floatsuffix = "f32" | "f64" ;
string  = '"' , { char | escape } , '"' ;
fstring = 'f"' , { char | escape | "{" expr "}" } , '"' ;
charlit = "'" , ( char | escape ) , "'" ;
```

## Program

```ebnf
program = { NL } , { item , { NL } } ;

item    = { attribute } , [ "pub" ] ,
          ( function | struct | enum | trait | impl
          | actor | typealias | const | import ) ;

attribute = "#" , ident , [ "(" , [ exprlist ] , ")" ] , [ "[" , [ exprlist ] , "]" ] ;
```

## Declarations

```ebnf
function = [ "async" ] , "fun" , ident , [ generics ] , params , [ "->" , type ] , block ;
generics = "<" , generic , { "," , generic } , ">" ;
generic  = ident , [ ":" , ident , { "+" , ident } ] ;
params   = "(" , [ param , { "," , param } ] , ")" ;
param    = [ "var" ] , "self"
         | ident , [ ":" , type ] ;

struct   = "struct" , ident , [ generics ] , "{" , { field , sep } , "}" ;
field    = ident , ":" , type ;

enum     = "enum" , ident , [ generics ] , "{" , { variant , sep } , "}" ;
variant  = ident , [ "(" , type , { "," , type } , ")" ] ;

trait    = "trait" , ident , [ generics ] , "{" , { function } , "}" ;
impl     = "impl" , [ generics ] , type , [ "for" , type ] , "{" , { function } , "}" ;
actor    = "actor" , ident , "{" , { field | function } , "}" ;

typealias = "typealias" , ident , "=" , type ;
const     = "const" , ident , ":" , type , "=" , expr ;
import    = "import" , dotted , [ "as" , ident ]
          | "from" , dotted , "import" , item , { "," , item } ;
```

## Types

```ebnf
type    = ident , [ "<" , type , { "," , type } , ">" ]
        | "(" , [ type , { "," , type } ] , ")" , [ "->" , type ]
        | "[" , type , [ ":" , type ] , "]"
        | "chan" , "<" , type , ">"
        | "self" ;
```

`( T )` is `T`; `( T, U )` is a tuple; `( T, U ) -> R` is a function type.
`[ T ]` is a list; `[ K : V ]` is a map.

## Statements

```ebnf
block   = "{" , { NL } , { statement , NL } , [ expr ] , "}" ;
statement = letstmt | assign | return | "break" | "continue"
          | while | for | select | expr ;
letstmt = ( "let" | "var" ) , ident , [ ":" , type ] , "=" , expr ;
assign  = lvalue , "=" , expr ;
lvalue  = ident | lvalue , "." , ident | lvalue , "[" , expr , "]" ;
return  = "return" , [ expr ] ;
while   = "while" , expr , block ;
for     = "for" , ident , "in" , expr , block ;
select  = "select" , "{" , { selectarm } , "}" ;
selectarm = [ ident , "=" ] , expr , "=>" , block ;
```

## Expressions

```ebnf
expr    = pipe ;
pipe    = range , { "|>" , range } ;
range   = binary , [ ".." , binary ] ;
binary  = (* precedence climbing; see language-spec §5 *) ;
unary   = ( "-" | "!" | "~" ) , unary | postfix , { "as" , type } ;
postfix = primary , { call | method | field | index | "?" } ;
call    = "(" , [ exprlist ] , ")" ;
method  = "." , ident , [ "(" , [ exprlist ] , ")" ] ;
index   = "[" , expr , "]" ;
primary = literal | ident | "self" | "_"
        | "(" , [ exprlist ] , ")"             (* group / tuple / lambda head *)
        | "(" , params , ")" , "=>" , expr     (* lambda *)
        | "[" , listbody , "]"                 (* list / map literal *)
        | ident , "{" , structfields , "}"     (* struct literal *)
        | block | ifexpr | matchexpr
        | "spawn" , expr | "await" , expr ;
ifexpr   = "if" , expr , block , [ "else" , ( ifexpr | block ) ] ;
matchexpr = "match" , expr , "{" , { matcharm } , "}" ;
matcharm = pattern , [ "if" , expr ] , "=>" , expr , [ "," ] ;
pattern  = patatom , { "|" , patatom } ;
patatom  = "_" | ident | literal
         | [ "." ] , ident , { "." , ident } , [ "(" , patterns , ")" ]
         | ident , "{" , { ident [ ":" pattern ] } , "}"
         | "(" , patterns , ")" ;
```

Struct literals are suppressed in control-flow conditions and match scrutinees
to disambiguate `Name { ... }` from a following block.
