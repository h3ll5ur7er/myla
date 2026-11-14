import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { parseExercise, parseChapter, idOf, buildCourse } from "../lib/learn.mjs";

const pages = { byPath: new Set(), byTitle: new Map(), tasks: new Map() };

test("an exercise's header, instructions and starter", () => {
  const ex = parseExercise("// title: Hello, Galaxy\n// xp: 15\n// expect: Hello, Galaxy!\n// hint: `print` adds the newline\n//\n// Make it **greet**.\n//\n// title: not a key here\nfun main() {\n    // TODO\n}\n");
  assert.equal(ex.title, "Hello, Galaxy");
  assert.equal(ex.xp, 15);
  assert.deepEqual(ex.expect, ["Hello, Galaxy!"]);
  assert.deepEqual(ex.hints, ["`print` adds the newline"]);
  assert.equal(ex.instructions, "Make it **greet**.\n\ntitle: not a key here");
  assert.equal(ex.starter, "fun main() {\n    // TODO\n}\n");
  assert.equal(ex.boss, false);
});

test("an exercise needs a title and positive xp", () => {
  assert.throws(() => parseExercise("// xp: 5\nfun main() {}\n"), /title/);
  assert.throws(() => parseExercise("// title: T\n// xp: 0\nfun main() {}\n"), /xp/);
});

test("a chapter's header and intro", () => {
  const ch = parseChapter("title: Don't Panic\nemoji: 🌌\ntagline: The basics\n\nWelcome *aboard*.\n");
  assert.deepEqual(ch, { title: "Don't Panic", emoji: "🌌", tagline: "The basics", intro: "Welcome *aboard*." });
  assert.throws(() => parseChapter("nope\n"), /key: value/);
});

test("ids drop the number", () => {
  assert.equal(idOf("01-hello-galaxy.my"), "hello-galaxy");
  assert.equal(idOf("03-the-grand-line"), "the-grand-line");
});

test("a course from a directory", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "learn-"));
  fs.mkdirSync(path.join(dir, "01-basics"));
  fs.writeFileSync(path.join(dir, "01-basics", "chapter.md"), "title: Basics\nemoji: 🚀\n\nHi.\n");
  fs.writeFileSync(path.join(dir, "01-basics", "01-one.my"), "// title: One\n// xp: 10\n#test()[1]\nfun one() -> int { return 0 }\n");
  fs.writeFileSync(path.join(dir, "01-basics", "01-one.solution.my"), "#test()[1]\nfun one() -> int { return 1 }\n");
  fs.writeFileSync(path.join(dir, "01-basics", "02-two.my"), "// title: Two\n// xp: 20\n// boss: true\n// expect: 2\nfun main() {}\n");
  fs.writeFileSync(path.join(dir, "01-basics", "02-two.solution.my"), "fun main() { print(2) }\n");
  const c = buildCourse(dir, pages);
  assert.equal(c.totalXp, 30);
  assert.equal(c.chapters[0].id, "basics");
  assert.deepEqual(c.chapters[0].exercises.map((e) => [e.id, e.mode, e.boss, e.expected]), [["one", "test", false, null], ["two", "output", true, "2\n"]]);
  assert.equal(c.chapters[0].exercises[1].solution, "fun main() { print(2) }\n");
  fs.rmSync(path.join(dir, "01-basics", "02-two.solution.my"));
  assert.throws(() => buildCourse(dir, pages), /no solution/);
});
