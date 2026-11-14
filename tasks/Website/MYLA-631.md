---
id: MYLA-631
title: "The website's content pipeline: the wiki's language and library pages as the site's docs"
type: feature
status: todo
priority: high
labels: [website, docs]
---
The wiki stays the single source (MYLA-159, D208): `website/scripts/content.mjs` turns `docs/Language.md`, `docs/Language/*.md`, `docs/Language/Standard-library*.md` and `docs/Getting-started.md` into JSON pages at build time: Markdown to HTML, `[[…]]` links to site routes (or to the repository on GitHub when the target isn't on the site), headings with anchors and a table of contents, and every `myla` code block an embedded editor ([[MYLA-633]]) with its expected output.

- [ ] The pipeline, with tests of its conversion (links, code blocks with `// output:`, `myla fragment`, `myla error`, tables, anchors)
- [ ] A `docs/Language/Builtins.md` wiki page: the builtin functions, the builtin methods and the implicit modules, so the reference has them from the wiki too
- [ ] The docs pages in the app: a sidebar of the pages, the page, its table of contents, previous and next
- [ ] The search index built with the pages
