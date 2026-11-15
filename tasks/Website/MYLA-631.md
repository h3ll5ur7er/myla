---
id: MYLA-631
title: "The website's content pipeline: the wiki's language and library pages as the site's docs"
type: feature
status: review
priority: high
labels: [website, docs]
---
The wiki stays the single source (MYLA-159, D208): `website/scripts/content.mjs` turns `docs/Language.md`, `docs/Language/*.md`, `docs/Language/Standard-library*.md` and `docs/Getting-started.md` into JSON pages at build time: Markdown to HTML, `[[…]]` links to site routes (or to the repository on GitHub when the target isn't on the site), headings with anchors and a table of contents, and every `myla` code block an embedded editor ([[MYLA-633]]) with its expected output.

- [x] The pipeline, with tests of its conversion (links, code blocks with `// output:`, `myla fragment`, `myla error`, tables, anchors)
- [x] The builtins page: the wiki's "Built-in functions" (docs/Language/Standard-library.md, which already holds them, so no second page) and the implicit modules' API
- [x] The docs pages in the app: a sidebar of the pages, the page, its table of contents, previous and next
- [x] The search index built with the pages

## Evidence

- `website/scripts/lib/markdown.mjs` and `content.mjs`: 15 language pages, 62 modules (their wiki pages joined with their API), the quickstart, the playground's examples (the repository's `examples/*.my`) and 2836 search entries in 1.8 s (`node scripts/prepare.mjs --skip-wasm`). Its tests (`node --test scripts/test/*.test.mjs`): 13, routes, wiki links (left alone inside code), anchors, examples with output and kind, tables, the course's format.
- The docs pages: a sidebar of the pages, the page with every `myla` block an editor, its contents with the section in view marked, previous and next, an edit link. Links route in the app and work under the base path; a link's anchor scrolls once the content is there.
