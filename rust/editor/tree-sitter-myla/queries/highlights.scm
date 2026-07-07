; Syntax highlighting for Myla.
;
; Capture names follow the nvim-treesitter conventions. Precedence note: when
; two patterns match the same node, the one defined *later* in this file wins
; (nvim-treesitter semantics). So the generic identifier fallback comes first,
; then heuristics, then the precise structural captures last.

; --- identifier fallback + naming heuristics -------------------------------

(identifier) @variable

; ALL_CAPS -> constant, CamelCase -> type (loose grammar heuristics)
((identifier) @type
  (#match? @type "^[A-Z]"))
((identifier) @constant
  (#match? @constant "^[A-Z][A-Z0-9_]+$"))

; --- literals --------------------------------------------------------------

(integer) @number
(float) @number.float
(string) @string
(fstring) @string
(char) @character
(boolean) @boolean

; --- comments --------------------------------------------------------------

(line_comment) @comment @spell
(block_comment) @comment @spell

; --- keywords --------------------------------------------------------------

"fun" @keyword.function
["let" "var" "const"] @keyword
["struct" "enum" "trait" "impl" "actor" "typealias"] @keyword.type
"return" @keyword.return
["if" "else" "match"] @keyword.conditional
["while" "for" "in" "break" "continue"] @keyword.repeat
["import" "from" "pub" "as"] @keyword.import
["async" "await"] @keyword.coroutine
["spawn" "go" "chan"] @keyword

; --- operators & punctuation ----------------------------------------------

[
  "+" "-" "*" "/" "%"
  "==" "!=" "<" "<=" ">" ">="
  "&&" "||" "!"
  "&" "|" "^" "~"
  "=" "|>" "->" "=>"
] @operator

["(" ")" "[" "]" "{" "}"] @punctuation.bracket
["," ":" "."] @punctuation.delimiter
"#" @punctuation.special

; --- self ------------------------------------------------------------------

"self" @variable.builtin

; --- attributes ------------------------------------------------------------

(attribute (identifier) @attribute)

; --- types -----------------------------------------------------------------

(named_type (identifier) @type)
(generic_param (identifier) @type.definition)
(chan_type "chan" @type.builtin)

((named_type (identifier) @type.builtin)
  (#any-of? @type.builtin
    "int" "int8" "int16" "int32" "int64"
    "uint8" "uint16" "uint32" "uint64"
    "float" "float32" "float64"
    "bool" "str" "char" "unit"))

; --- declarations ----------------------------------------------------------

(function name: (identifier) @function)
(struct (identifier) @type)
(enum (identifier) @type)
(trait (identifier) @type)
(actor (identifier) @type)
(typealias (identifier) @type)
(const (identifier) @constant)
(variant (identifier) @constructor)

(param . (identifier) @variable.parameter)
(field . (identifier) @variable.member)
(let_statement . (identifier) @variable)
(for_statement . (identifier) @variable)
(dotted_path (identifier) @module)

; --- calls & member access -------------------------------------------------

(field_access (identifier) @variable.member .)

(call
  . (identifier) @function.call)
(call
  . (field_access (identifier) @function.method.call .))
