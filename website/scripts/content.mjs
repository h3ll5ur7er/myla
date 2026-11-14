// content.mjs: the website's content from the wiki, the API reference and
// the exercises (MYLA-631, MYLA-632, MYLA-634, D208).
//
//   node scripts/content.mjs <api.json> <out dir>
//
// writes, below <out dir>:
//   site.json            the navigation: docs pages, reference modules, chapters
//   search.json          the search index
//   docs/<slug>.json     a language page: title, HTML, examples, contents
//   reference/<m>.json   a module: its wiki page (if any) and its API
//   learn.json           the course (scripts/lib/learn.mjs)

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { convertPage, inlineDoc, plainText, slugify } from "./lib/markdown.mjs";
import { buildCourse } from "./lib/learn.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const REPO_ROOT = path.resolve(HERE, "../..");
const DOCS = path.join(REPO_ROOT, "docs");

// The modules whose methods every program has: the built-in types' methods.
export const IMPLICIT = ["str", "char", "int", "float", "list", "map", "option", "hash"];

// The reference's groups of modules, in their order; a module in none is
// in "More".
export const GROUPS = [
  ["Built-in types", IMPLICIT],
  ["Input, output and the system", ["io", "ioerror", "fs", "path", "glob", "process", "args", "signal", "term", "log", "time", "platform"]],
  ["Text and data formats", ["text", "fmt", "regex", "bytes", "encoding", "json", "toml", "yaml", "xml", "ini", "csv", "url", "uuid"]],
  ["Collections", ["iter", "set", "deque", "heap", "btree", "bitset", "graph", "grid", "unionfind", "cache"]],
  ["Numbers and maths", ["num", "math", "bigint", "random", "algebra", "vector", "matrix", "quaternion", "vector32", "matrix32", "quaternion32"]],
  ["Networking and concurrency", ["task", "net", "http"]],
  ["Compression, archives and digests", ["compress", "archive", "checksum", "digest"]],
  ["Testing and measuring", ["test", "bench"]],
];

function walk(dir) {
  const out = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...walk(p));
    else if (e.name.endsWith(".md")) out.push(p);
  }
  return out;
}

// Every wiki page by path and title, and every task's file, for links.
function pageIndex() {
  const byPath = new Set();
  const byTitle = new Map();
  for (const f of walk(DOCS)) {
    const rel = path.relative(DOCS, f).replace(/\\/g, "/").replace(/\.md$/, "");
    byPath.add(rel);
    const title = rel.split("/").pop().replace(/-/g, " ").toLowerCase();
    if (!byTitle.has(title)) byTitle.set(title, rel);
    if (!byTitle.has(rel.split("/").pop().toLowerCase())) byTitle.set(rel.split("/").pop().toLowerCase(), rel);
  }
  const tasks = new Map();
  for (const f of walkAll(path.join(REPO_ROOT, "tasks"))) {
    const m = /(MYLA-\d+)\.md$/.exec(f);
    if (m) tasks.set(m[1], path.relative(REPO_ROOT, f).replace(/\\/g, "/"));
  }
  return { byPath, byTitle, tasks };
}

function walkAll(dir) {
  if (!fs.existsSync(dir)) return [];
  const out = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...walkAll(p));
    else out.push(p);
  }
  return out;
}

function read(rel) {
  return fs.readFileSync(path.join(DOCS, rel), "utf8");
}

function writeJson(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(value));
}

// The language pages in the order Language.md's table of pages lists them.
function languageOrder() {
  const md = read("Language.md");
  const order = [];
  for (const m of md.matchAll(/\[\[Language\/([A-Za-z-]+)\]\]/g)) {
    if (m[1] !== "Standard-library" && !order.includes(m[1])) order.push(m[1]);
  }
  for (const f of fs.readdirSync(path.join(DOCS, "Language"))) {
    const name = f.replace(/\.md$/, "");
    if (f.endsWith(".md") && name !== "Standard-library" && !order.includes(name)) order.push(name);
  }
  return order;
}

// The one-line summaries of the modules: Standard-library.md's table.
function moduleSummaries() {
  const md = read("Language/Standard-library.md");
  const out = new Map();
  for (const line of md.split("\n")) {
    const m = /^\| `std\.([a-z0-9_]+)` \| [^|]*\| (.*) \|\s*$/.exec(line);
    if (m) out.set(m[1], m[2]);
  }
  return out;
}

// An API item for the page: its doc as HTML, its examples, an anchor.
function apiItem(item, pages, ids) {
  let id = slugify(item.kind === "impl" ? `impl ${item.trait_name || ""} ${item.target}` : `${item.kind} ${item.name}`);
  const n = ids.get(id) ?? 0;
  ids.set(id, n + 1);
  if (n) id = `${id}-${n}`;
  return {
    id,
    name: item.name,
    kind: item.kind,
    signature: item.signature,
    doc: item.doc ? inlineDoc(item.doc, pages) : "",
    tests: item.tests,
    line: item.line,
    target: item.target,
    trait: item.trait_name,
    members: item.members.map((m) => ({
      name: m.name,
      kind: m.kind,
      signature: m.signature,
      doc: m.doc ? inlineDoc(m.doc, pages) : "",
      tests: m.tests,
      line: m.line,
    })),
  };
}

export function buildContent(apiPath, outDir) {
  const pages = pageIndex();
  const search = [];
  const site = { docs: [], reference: [], groups: [], chapters: [] };

  // --- the language docs -----------------------------------------------------------
  const order = languageOrder();
  const docPages = [{ file: "Language.md", slug: "" }, ...order.map((n) => ({ file: `Language/${n}.md`, slug: n.toLowerCase() }))];
  const converted = docPages.map((p) => ({ ...p, page: convertPage(read(p.file), { ...pages, subpages: "" }) }));
  converted.forEach((p, i) => {
    const prev = converted[i - 1];
    const next = converted[i + 1];
    const route = p.slug ? `/docs/${p.slug}` : "/docs";
    writeJson(path.join(outDir, "docs", `${p.slug || "index"}.json`), {
      slug: p.slug,
      title: p.page.title,
      html: p.page.html,
      examples: p.page.examples,
      toc: p.page.toc,
      source: `docs/${p.file}`,
      prev: prev ? { title: prev.page.title, route: prev.slug ? `/docs/${prev.slug}` : "/docs" } : null,
      next: next ? { title: next.page.title, route: `/docs/${next.slug}` } : null,
    });
    site.docs.push({ slug: p.slug, title: p.page.title, route, sections: p.page.toc.filter((t) => t.level === 2).length });
    search.push({ t: p.page.title, u: route, k: "Docs", d: plainText(p.page.html, 110) });
    for (const t of p.page.toc) search.push({ t: t.text, u: `${route}#${t.id}`, k: "Docs", d: p.page.title });
  });

  // the quickstart's second half: the wiki's Getting-started page
  const gs = convertPage(read("Getting-started.md"), { ...pages, subpages: "" });
  writeJson(path.join(outDir, "quickstart.json"), { slug: "quickstart", title: gs.title, html: gs.html, examples: gs.examples, toc: gs.toc, source: "docs/Getting-started.md", prev: null, next: null });
  search.push({ t: "Quickstart", u: "/quickstart", k: "Docs", d: plainText(gs.html, 110) });
  for (const t of gs.toc) search.push({ t: t.text, u: `/quickstart#${t.id}`, k: "Docs", d: "Quickstart" });

  // --- the reference -----------------------------------------------------------------
  const api = new Map(JSON.parse(fs.readFileSync(apiPath, "utf8")).map((m) => [m.name.replace(/^std\./, ""), m]));
  const summaries = moduleSummaries();
  const wikiModules = new Map();
  for (const f of fs.readdirSync(path.join(DOCS, "Language/Standard-library"))) {
    if (f.endsWith(".md")) wikiModules.set(f.replace(/\.md$/, "").toLowerCase(), `Language/Standard-library/${f}`);
  }
  const names = [...new Set([...api.keys()])].sort();
  for (const name of names) {
    const m = api.get(name);
    const wikiFile = wikiModules.get(name);
    const wiki = wikiFile ? convertPage(read(wikiFile), { ...pages, subpages: "" }) : null;
    const ids = new Map();
    const items = m.items.map((it) => apiItem(it, pages, ids));
    const route = `/reference/${name}`;
    writeJson(path.join(outDir, "reference", `${name}.json`), {
      name: `std.${name}`,
      slug: name,
      implicit: IMPLICIT.includes(name),
      summary: summaries.get(name) ? inlineDoc(summaries.get(name), pages) : "",
      moduleDoc: m.doc,
      wiki: wiki ? { title: wiki.title, html: wiki.html, examples: wiki.examples, toc: wiki.toc, source: `docs/${wikiFile}` } : null,
      items,
      source: m.path.replace(/^.*?(lib\/std\/)/, "$1"),
    });
    const summary = summaries.get(name) ?? m.doc.split("\n")[0].replace(/^std\.[a-z0-9_]+:\s*/, "");
    site.reference.push({ name: `std.${name}`, slug: name, route, summary: plainText(inlineDoc(summary, pages), 140), items: items.length, implicit: IMPLICIT.includes(name) });
    search.push({ t: `std.${name}`, u: route, k: "Module", d: plainText(inlineDoc(summary, pages), 110) });
    for (const it of items) {
      if (it.kind === "impl") {
        for (const mem of it.members) search.push({ t: `${it.target}.${mem.name}`, u: `${route}#${it.id}`, k: "Method", d: `std.${name} · ${mem.signature}` });
      } else {
        search.push({ t: it.name, u: `${route}#${it.id}`, k: kindLabel(it.kind), d: `std.${name} · ${it.signature}` });
        for (const mem of it.members) {
          if (mem.kind === "method") search.push({ t: `${it.name}.${mem.name}`, u: `${route}#${it.id}`, k: "Method", d: `std.${name} · ${mem.signature}` });
        }
      }
    }
  }
  const placed = new Set();
  for (const [title, mods] of GROUPS) {
    const present = mods.filter((n) => api.has(n));
    present.forEach((n) => placed.add(n));
    site.groups.push({ title, modules: present });
  }
  const more = names.filter((n) => !placed.has(n));
  if (more.length) site.groups.push({ title: "More", modules: more });

  // the reference's front page and the builtins: Standard-library.md
  const lib = convertPage(read("Language/Standard-library.md"), { ...pages, subpages: "" });
  writeJson(path.join(outDir, "reference", "index.json"), { title: lib.title, html: lib.html, examples: lib.examples, toc: lib.toc, source: "docs/Language/Standard-library.md" });
  search.push({ t: "Built-in functions", u: "/reference/builtins", k: "Reference", d: "print, format, assert, panic, the methods of the built-in types" });

  // --- the course --------------------------------------------------------------------
  const course = buildCourse(path.join(REPO_ROOT, "learn"), pages);
  writeJson(path.join(outDir, "learn.json"), course);
  for (const ch of course.chapters) {
    site.chapters.push({ id: ch.id, title: ch.title, emoji: ch.emoji, exercises: ch.exercises.length });
    search.push({ t: ch.title, u: `/learn/${ch.id}`, k: "Learn", d: ch.tagline });
    for (const ex of ch.exercises) search.push({ t: ex.title, u: `/learn/${ch.id}/${ex.id}`, k: "Exercise", d: ch.title });
  }

  // --- the playground's examples: the repository's single-file examples --------------
  const exDir = path.join(REPO_ROOT, "examples");
  const examples = fs
    .readdirSync(exDir)
    .filter((f) => f.endsWith(".my"))
    .sort()
    .map((f) => {
      const source = fs.readFileSync(path.join(exDir, f), "utf8");
      const first = source.split("\n").find((l) => l.startsWith("//"));
      return { file: f, title: f.replace(/\.my$/, "").replace(/[_-]/g, " "), about: first ? first.replace(/^\/\/\s?/, "") : "", source };
    });
  writeJson(path.join(outDir, "playground.json"), examples);

  writeJson(path.join(outDir, "site.json"), site);
  writeJson(path.join(outDir, "search.json"), search);
  return { docs: site.docs.length, modules: site.reference.length, chapters: course.chapters.length, exercises: course.chapters.reduce((s, c) => s + c.exercises.length, 0), search: search.length };
}

function kindLabel(k) {
  return { function: "Function", struct: "Struct", enum: "Enum", trait: "Trait", constant: "Constant", type: "Type" }[k] ?? "Item";
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const [apiPath, outDir] = process.argv.slice(2);
  if (!apiPath || !outDir) {
    console.error("usage: node scripts/content.mjs <api.json> <out dir>");
    process.exit(2);
  }
  const stats = buildContent(apiPath, outDir);
  console.log(`content: ${stats.docs} docs pages, ${stats.modules} modules, ${stats.chapters} chapters (${stats.exercises} exercises), ${stats.search} search entries`);
}

