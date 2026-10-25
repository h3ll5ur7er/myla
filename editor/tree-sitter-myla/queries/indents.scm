; Indentation for Myla (nvim-treesitter `indent` module).
;
; @indent.begin   — indent the lines inside this node one level
; @indent.end     — the closing token that dedents back
; @indent.branch  — a line that should align with the block opener (e.g. else)

[
  (block)
  (params)
  (generics)
  (list)
  (map)
  (tuple)
  (struct)
  (enum)
  (trait)
  (impl)
  (actor)
  (match_expr)
] @indent.begin

[
  "}"
  "]"
  ")"
] @indent.end

"else" @indent.branch
