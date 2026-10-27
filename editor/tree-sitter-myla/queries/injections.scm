; Language injections for Myla: the `comment` grammar in comments, so that
; TODO/FIXME/NOTE markers are highlighted.

((comment) @injection.content
  (#set! injection.language "comment"))
