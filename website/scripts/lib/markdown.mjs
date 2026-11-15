// markdown.mjs: the wiki's Markdown as the website's HTML (MYLA-631, D208).
//
// The wiki is the single source of the site's docs. A page is converted at
// build time: `[[…]]` links become links to the site's routes (or to the
// repository on GitHub when the target isn't on the site), headings get
// anchors and a table of contents, and every `myla` code block becomes an
// embedded editor: a placeholder `<div class="myla-example" data-i="N">`
// in the HTML and the N-th entry of the page's `examples`.

import { Marked } from "marked";

export const REPO = "https://github.com/h3ll5ur7er/myla";
export const BLOB = `${REPO}/blob/master`;

// The site's route of a wiki page (its path below docs/, without .md), or
// null when the page isn't on the site.
export function routeOf(page) {
  const p = page.replace(/\.md$/, "");
  if (p === "Language") return "/docs";
  if (p === "Language/Standard-library") return "/reference";
  if (p === "Getting-started") return "/quickstart";
  let m = /^Language\/Standard-library\/([A-Za-z0-9-]+)$/.exec(p);
  if (m) return `/reference/${m[1].toLowerCase()}`;
  m = /^Language\/([A-Za-z0-9-]+)$/.exec(p);
  if (m) return `/docs/${m[1].toLowerCase()}`;
  return null;
}

// Where a `[[…]]` target points: a site route, or the repository.
export function wikiHref(target, pages) {
  const [path, anchor] = splitAnchor(target);
  const hash = anchor ? `#${slugify(anchor)}` : "";
  if (/^MYLA-\d+$/.test(path)) {
    const file = pages.tasks?.get(path);
    return file ? `${BLOB}/${encodePath(file)}` : `${REPO}/tree/master/tasks`;
  }
  // a page by its path, or by its title (the last segment)
  const page = pages.byPath.has(path) ? path : pages.byTitle.get(path.toLowerCase());
  if (page) {
    const route = routeOf(page);
    if (route) return route + hash;
    return `${BLOB}/docs/${encodePath(page)}.md${hash}`;
  }
  // a file of the repository, perhaps with lines: `lib/std/io.my#L10-L20`
  const lines = anchor && /^L\d+(-L\d+)?$/.test(anchor) ? `#${anchor}` : hash;
  return `${BLOB}/${encodePath(path)}${lines}`;
}

function splitAnchor(target) {
  const i = target.indexOf("#");
  return i < 0 ? [target, ""] : [target.slice(0, i), target.slice(i + 1)];
}

function encodePath(p) {
  return p.split("/").map(encodeURIComponent).join("/");
}

// A heading's anchor, as GitHub makes them: lower case, punctuation dropped,
// spaces to hyphens.
export function slugify(text) {
  return text
    .toLowerCase()
    .replace(/<[^>]+>/g, "")
    .replace(/[`*_~]/g, "")
    .replace(/[^\p{L}\p{N}\s-]/gu, "")
    .trim()
    .replace(/\s+/g, "-");
}

// The text shown for a `[[target]]` link without its own text: a page's
// title as the wiki shows it, a file's path, a task's id.
function linkText(target) {
  const [path, anchor] = splitAnchor(target);
  const last = path.split("/").pop().replace(/-/g, " ");
  if (/^MYLA-\d+$/.test(path) || path.includes(".")) return target;
  return anchor ? `${last} § ${anchor.replace(/-/g, " ")}` : last;
}

// `[[target]]` and `[[target|text]]` as Markdown links, outside code.
export function rewriteWikiLinks(md, pages) {
  return mapOutsideCode(md, (text) =>
    text.replace(/\[\[([^\]|]+?)(?:\|([^\]]+))?\]\]/g, (_, target, label) => {
      const href = wikiHref(target.trim(), pages);
      return `[${escapeBrackets(label ?? linkText(target.trim()))}](${href.replace(/ /g, "%20")})`;
    }),
  );
}

function escapeBrackets(s) {
  return s.replace(/([\[\]])/g, "\\$1");
}

// `f` applied to the parts of `md` outside fenced code blocks and inline
// code spans.
export function mapOutsideCode(md, f) {
  const out = [];
  const lines = md.split("\n");
  let fence = null;
  let buf = [];
  const flush = () => {
    if (buf.length) out.push(mapOutsideSpans(buf.join("\n"), f));
    buf = [];
  };
  for (const line of lines) {
    const m = /^\s*(```+|~~~+)/.exec(line);
    if (fence) {
      out.push(line);
      if (m && m[1][0] === fence[0] && m[1].length >= fence.length && line.trim() === m[1]) fence = null;
    } else if (m) {
      flush();
      fence = m[1];
      out.push(line);
    } else {
      buf.push(line);
    }
  }
  flush();
  return out.join("\n");
}

function mapOutsideSpans(text, f) {
  let out = "";
  let i = 0;
  while (i < text.length) {
    const j = text.indexOf("`", i);
    if (j < 0) {
      out += f(text.slice(i));
      break;
    }
    out += f(text.slice(i, j));
    let n = 0;
    while (text[j + n] === "`") n++;
    const ticks = "`".repeat(n);
    const end = text.indexOf(ticks, j + n);
    if (end < 0) {
      out += text.slice(j);
      break;
    }
    out += text.slice(j, end + n);
    i = end + n;
  }
  return out;
}

// A `myla` block's source, its expected output (from its trailing
// `// output:` comment, `//` alone an empty line) and its kind: `run` (it has
// a `main`), `check` (it hasn't), `fragment` (a piece of a program, shown
// only) or `error` (meant to fail the checker).
export function parseExample(code, info) {
  const words = info.trim().split(/\s+/).slice(1);
  let kind = words.includes("fragment") ? "fragment" : words.includes("error") ? "error" : null;
  const lines = code.replace(/\s+$/, "").split("\n");
  let output = null;
  const at = lines.findIndex((l) => /^\/\/ output:\s*$/.test(l));
  if (at >= 0 && lines.slice(at + 1).every((l) => /^\/\/( |$)/.test(l))) {
    output = lines.slice(at + 1).map((l) => (l === "//" ? "" : l.slice(3))).join("\n") + "\n";
    lines.length = at;
  }
  const source = lines.join("\n").replace(/\s+$/, "") + "\n";
  if (!kind) kind = /^\s*(async\s+)?fun\s+main\s*\(/m.test(source) ? "run" : "check";
  return { source, output, kind };
}

// A page converted: its title (the first `#` heading), HTML, examples and
// table of contents (the `##` and `###` headings).
export function convertPage(md, pages) {
  const examples = [];
  const toc = [];
  let title = null;
  const used = new Map();
  const marked = new Marked({ gfm: true });
  marked.use({
    renderer: {
      heading({ tokens, depth, text }) {
        const html = this.parser.parseInline(tokens);
        if (depth === 1 && title === null) {
          title = stripTags(html);
          return "";
        }
        let id = slugify(text);
        const n = used.get(id) ?? 0;
        used.set(id, n + 1);
        if (n) id = `${id}-${n}`;
        if (depth <= 3) toc.push({ id, text: stripTags(html), level: depth });
        return `<h${depth} id="${id}"><a class="anchor" href="#${id}" aria-hidden="true">#</a>${html}</h${depth}>\n`;
      },
      code({ text, lang }) {
        const info = lang ?? "";
        if (info.split(/\s+/)[0] === "myla") {
          examples.push(parseExample(text, info));
          return `<div class="myla-example" data-i="${examples.length - 1}"></div>\n`;
        }
        const cls = info ? ` class="language-${escapeHtml(info.split(/\s+/)[0])}"` : "";
        return `<pre class="code-block"><code${cls}>${escapeHtml(text)}</code></pre>\n`;
      },
      table(token) {
        // tables scroll on their own on a narrow screen
        return `<div class="table-wrap">${marked.Renderer.prototype.table.call(this, token)}</div>\n`;
      },
      link({ href, title: t, tokens }) {
        const html = this.parser.parseInline(tokens);
        const external = /^https?:/.test(href);
        const attrs = external ? ' target="_blank" rel="noopener"' : "";
        const tt = t ? ` title="${escapeHtml(t)}"` : "";
        return `<a href="${escapeHtml(href)}"${tt}${attrs}>${html}</a>`;
      },
    },
  });
  let body = md.replace(/^\[TOC\]\s*$/m, "");
  body = body.replace(/^\[SUBPAGES\]\s*$/m, () => (pages.subpages ? pages.subpages : ""));
  const html = marked.parse(rewriteWikiLinks(body, pages));
  return { title: title ?? "", html, examples, toc };
}

function stripTags(html) {
  return html.replace(/<[^>]+>/g, "").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'");
}

export function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// Markdown of a doc comment (from the API reference) as HTML.
export function inlineDoc(md, pages) {
  const marked = new Marked({ gfm: true });
  return marked.parse(rewriteWikiLinks(md, pages));
}

// The plain text of some HTML, for the search index: tags dropped,
// whitespace collapsed, at most `max` characters.
export function plainText(html, max = 200) {
  const t = stripTags(html).replace(/\s+/g, " ").trim();
  return t.length > max ? t.slice(0, max - 1) + "…" : t;
}
