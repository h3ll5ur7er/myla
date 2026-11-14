// learn.mjs: the course from learn/ (MYLA-634, D208).
//
// learn/<NN-chapter>/chapter.md is a chapter: a header of `key: value`
// lines (title, emoji, tagline) up to a blank line, then its introduction in
// Markdown. Beside it, each exercise is `<NN-name>.my`, and its solution
// `<NN-name>.solution.my`. An exercise starts with a header of `//` lines:
//
//   // title: Hello, Galaxy
//   // xp: 10
//   // boss: true                  (optional: the chapter's final exercise)
//   // expect: Hello, Galaxy!      (optional, one line each: what it prints)
//   // hint: print adds the newline itself
//   //
//   // The instructions, in Markdown, to the header's end.
//
// The header ends at the first line that isn't a comment. An exercise with
// `expect:` lines is solved when running it prints exactly them; one without
// is solved when its #test cases pass. CI checks that every exercise as
// given isn't solved and its solution is (tests/burn/test_learn.py).

import fs from "node:fs";
import path from "node:path";
import { convertPage, inlineDoc } from "./markdown.mjs";

const KEYS = new Set(["title", "xp", "boss", "expect", "hint"]);

// An exercise's header and its code (the starter shown in the editor).
export function parseExercise(text) {
  const lines = text.split("\n");
  const ex = { title: "", xp: 10, boss: false, expect: [], hints: [], instructions: "", starter: "" };
  const prose = [];
  let i = 0;
  let inProse = false;
  for (; i < lines.length; i++) {
    const m = /^\/\/ ?(.*)$/.exec(lines[i]);
    if (!m) break;
    const body = m[1];
    const kv = /^([a-z]+): ?(.*)$/.exec(body);
    if (!inProse && kv && KEYS.has(kv[1])) {
      const [, k, v] = kv;
      if (k === "title") ex.title = v.trim();
      else if (k === "xp") ex.xp = parseInt(v, 10);
      else if (k === "boss") ex.boss = v.trim() === "true";
      else if (k === "expect") ex.expect.push(v);
      else if (k === "hint") ex.hints.push(v.trim());
    } else {
      inProse = true;
      prose.push(body);
    }
  }
  ex.instructions = prose.join("\n").trim();
  ex.starter = lines.slice(i).join("\n").replace(/^\n+/, "").replace(/\s+$/, "") + "\n";
  if (!ex.title) throw new Error("an exercise needs a `// title:`");
  if (!Number.isFinite(ex.xp) || ex.xp <= 0) throw new Error(`${ex.title}: \`// xp:\` must be a positive number`);
  return ex;
}

// A chapter's header (`key: value` lines) and its introduction.
export function parseChapter(text) {
  const lines = text.split("\n");
  const meta = {};
  let i = 0;
  for (; i < lines.length && lines[i].trim() !== ""; i++) {
    const m = /^([a-z]+):\s*(.*)$/.exec(lines[i]);
    if (!m) throw new Error(`chapter.md: line ${i + 1} isn't \`key: value\``);
    meta[m[1]] = m[2].trim();
  }
  if (!meta.title) throw new Error("chapter.md needs a `title:`");
  return { title: meta.title, emoji: meta.emoji ?? "📘", tagline: meta.tagline ?? "", intro: lines.slice(i).join("\n").trim() };
}

// The id of a chapter or exercise: its file name without the number.
export function idOf(name) {
  return name.replace(/\.my$/, "").replace(/^\d+-/, "");
}

export function buildCourse(dir, pages) {
  const chapters = [];
  if (!fs.existsSync(dir)) return { chapters, totalXp: 0 };
  const dirs = fs.readdirSync(dir, { withFileTypes: true }).filter((e) => e.isDirectory() && /^\d+-/.test(e.name)).map((e) => e.name).sort();
  for (const d of dirs) {
    const chDir = path.join(dir, d);
    const ch = parseChapter(fs.readFileSync(path.join(chDir, "chapter.md"), "utf8"));
    const files = fs.readdirSync(chDir).filter((f) => /^\d+-.*\.my$/.test(f) && !f.endsWith(".solution.my")).sort();
    const exercises = files.map((f) => {
      const ex = parseExercise(fs.readFileSync(path.join(chDir, f), "utf8"));
      const solFile = path.join(chDir, f.replace(/\.my$/, ".solution.my"));
      if (!fs.existsSync(solFile)) throw new Error(`${d}/${f} has no solution beside it`);
      return {
        id: idOf(f),
        file: `learn/${d}/${f}`,
        title: ex.title,
        xp: ex.xp,
        boss: ex.boss,
        mode: ex.expect.length ? "output" : "test",
        expected: ex.expect.length ? ex.expect.join("\n") + "\n" : null,
        hints: ex.hints.map((h) => inlineDoc(h, pages).replace(/^<p>|<\/p>\n?$/g, "")),
        instructions: inlineDoc(ex.instructions, pages),
        starter: ex.starter,
        solution: fs.readFileSync(solFile, "utf8"),
      };
    });
    chapters.push({ id: idOf(d), title: ch.title, emoji: ch.emoji, tagline: ch.tagline, intro: convertPage(ch.intro, pages).html, exercises });
  }
  const totalXp = chapters.reduce((s, c) => s + c.exercises.reduce((t, e) => t + e.xp, 0), 0);
  return { chapters, totalXp };
}
