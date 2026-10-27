; Indentation for Myla (nvim-treesitter `indent` module).
;
; @indent.begin   indent the lines inside this node one level
; @indent.end     the closing token that dedents back
; @indent.branch  a line that aligns with the block opener (else)

[
  (block)
  (struct_decl)
  (enum_decl)
  (impl_decl)
  (trait_decl)
  (match_expr)
  (struct_literal)
  (struct_pattern)
  (list)
  (map)
  (call_args)
  (expr_list)
] @indent.begin

[
  "}"
  "]"
  ")"
] @indent.end

"else" @indent.branch
