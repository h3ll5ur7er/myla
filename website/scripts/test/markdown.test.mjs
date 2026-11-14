import { test } from "node:test";
import assert from "node:assert/strict";
import { routeOf, wikiHref, slugify, rewriteWikiLinks, parseExample, convertPage, BLOB, plainText } from "../lib/markdown.mjs";

const pages = {
  byPath: new Set(["Language", "Language/Types", "Language/Standard-library", "Language/Standard-library/Json", "Project/Decisions", "Getting-started"]),
  byTitle: new Map([["types", "Language/Types"], ["decisions", "Project/Decisions"]]),
  tasks: new Map([["MYLA-12", "tasks/Language/MYLA-12.md"]]),
};

test("routes of wiki pages", () => {
  assert.equal(routeOf("Language"), "/docs");
  assert.equal(routeOf("Language/Types"), "/docs/types");
  assert.equal(routeOf("Language/Standard-library"), "/reference");
  assert.equal(routeOf("Language/Standard-library/Json.md"), "/reference/json");
  assert.equal(routeOf("Getting-started"), "/quickstart");
  assert.equal(routeOf("Project/Decisions"), null);
});

test("wiki links: pages, titles, anchors, tasks and files", () => {
  assert.equal(wikiHref("Language/Types", pages), "/docs/types");
  assert.equal(wikiHref("Types", pages), "/docs/types");
  assert.equal(wikiHref("Language/Types#Function types", pages), "/docs/types#function-types");
  assert.equal(wikiHref("Project/Decisions", pages), `${BLOB}/docs/Project/Decisions.md`);
  assert.equal(wikiHref("MYLA-12", pages), `${BLOB}/tasks/Language/MYLA-12.md`);
  assert.equal(wikiHref("lib/std/io.my#L10-L20", pages), `${BLOB}/lib/std/io.my#L10-L20`);
});

test("wiki links are left alone inside code", () => {
  const md = "See [[Language/Types]] and `[[not a link]]`.\n\n```myla\n// [[nor this]]\n```\n";
  const out = rewriteWikiLinks(md, pages);
  assert.match(out, /\[Types\]\(\/docs\/types\)/);
  assert.match(out, /`\[\[not a link\]\]`/);
  assert.match(out, /\/\/ \[\[nor this\]\]/);
  assert.match(rewriteWikiLinks("[[Project/Decisions|the decisions]]", pages), /^\[the decisions\]\(https:/);
});

test("slugs as GitHub makes them", () => {
  assert.equal(slugify("Function types"), "function-types");
  assert.equal(slugify("`Option` and `Result`!"), "option-and-result");
  assert.equal(slugify("D89: async/await"), "d89-asyncawait");
});

test("a myla block: its output and its kind", () => {
  const e = parseExample("fun main() {\n    print(42)\n    print(\"\")\n}\n// output:\n// 42\n//\n", "myla");
  assert.equal(e.kind, "run");
  assert.equal(e.output, "42\n\n");
  assert.equal(e.source, "fun main() {\n    print(42)\n    print(\"\")\n}\n");
  assert.equal(parseExample("fun f() -> int { return 1 }", "myla").kind, "check");
  assert.equal(parseExample("let x = 1", "myla fragment").kind, "fragment");
  assert.equal(parseExample("fun main() { print(1 + true) }", "myla error").kind, "error");
  assert.equal(parseExample("#main\nasync fun main() {}", "myla").kind, "run");
  // an `// output:` that isn't the block's end is part of the source
  assert.equal(parseExample("// output: below\nfun main() {}\n", "myla").output, null);
});

test("a page: title, anchors, table of contents, examples, tables", () => {
  const md = "# Types\n\nIntro.\n\n[TOC]\n\n## Integers\n\n```myla\nfun main() { print(1) }\n// output:\n// 1\n```\n\n## Integers\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n";
  const p = convertPage(md, pages);
  assert.equal(p.title, "Types");
  assert.deepEqual(p.toc, [{ id: "integers", text: "Integers", level: 2 }, { id: "integers-1", text: "Integers", level: 2 }]);
  assert.equal(p.examples.length, 1);
  assert.equal(p.examples[0].output, "1\n");
  assert.match(p.html, /<div class="myla-example" data-i="0"><\/div>/);
  assert.match(p.html, /<h2 id="integers-1">/);
  assert.match(p.html, /<div class="table-wrap"><table>/);
  assert.doesNotMatch(p.html, /\[TOC\]/);
  assert.doesNotMatch(p.html, /<h1/);
});

test("other code blocks stay code, escaped", () => {
  const p = convertPage("```bash\necho <hi>\n```\n", pages);
  assert.match(p.html, /<pre class="code-block"><code class="language-bash">echo &lt;hi&gt;\n?<\/code><\/pre>/);
});

test("plain text for the search index", () => {
  assert.equal(plainText("<p>A <code>b</code>   c</p>"), "A b c");
  assert.equal(plainText("<p>" + "x".repeat(300) + "</p>", 10), "xxxxxxxxx…");
});
