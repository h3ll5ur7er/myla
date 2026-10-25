; Language injections for Myla.
;
; Inject the `comment` grammar into comments so TODO/FIXME/NOTE tags and similar
; markers get highlighted. (Myla f-strings are lexed as a single token, so their
; `{ ... }` holes are not yet available for an embedded-Myla injection.)

((line_comment) @injection.content
  (#set! injection.language "comment"))

((block_comment) @injection.content
  (#set! injection.language "comment"))
