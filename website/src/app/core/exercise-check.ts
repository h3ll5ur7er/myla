// What the Check button runs for an exercise checked by its tests (MYLA-634).
//
// The learner's #test cases don't count: they could delete the given ones
// and write a trivial one. So every `#test` in the learner's code is
// removed, and the exercise's own cases (the starter's) and its hidden ones
// are put back above their functions. An exercise about writing tests
// (`// own-tests: N`) keeps the learner's cases instead, adds the hidden
// ones, and needs N of the learner's own.
//
// No imports: scripts/check-course.mjs runs this file under Node (types
// stripped), and tests/burn/test_website.py does the same in Python.

export interface TestBlock {
  fn: string;
  lines: string[];
}

const FUN = /^(\s*)(?:pub\s+)?(?:async\s+)?fun\s+([A-Za-z_][A-Za-z0-9_]*)\s*[<(]/;

// The end (exclusive) of the attribute starting on line `i`: the line where
// its brackets close, strings skipped.
function attributeEnd(lines: string[], i: number): number {
  let depth = 0;
  let inString = false;
  for (let j = i; j < lines.length; j++) {
    const l = lines[j];
    for (let k = 0; k < l.length; k++) {
      const c = l[k];
      if (inString) {
        if (c === '\\') k++;
        else if (c === '"') inString = false;
      } else if (c === '"') inString = true;
      else if (c === '(' || c === '[') depth++;
      else if (c === ')' || c === ']') depth--;
    }
    // a case is `#test(…)[…]`: done once something opened and all closed
    if (depth <= 0 && /[\])]\s*$/.test(l)) return j + 1;
  }
  return lines.length;
}

// The #test cases of `source`, by the function they sit above.
export function testsOf(source: string): TestBlock[] {
  const lines = source.split('\n');
  const out: TestBlock[] = [];
  let pending: string[] = [];
  for (let i = 0; i < lines.length; ) {
    const t = lines[i].trim();
    if (t.startsWith('#test')) {
      const end = attributeEnd(lines, i);
      pending.push(lines.slice(i, end).join('\n').trim());
      i = end;
      continue;
    }
    const m = FUN.exec(lines[i]);
    if (m && pending.length) out.push({ fn: m[2], lines: pending });
    if (!t.startsWith('#')) pending = [];
    i++;
  }
  return out;
}

// The program Check runs: `code` with the learner's cases replaced by `own`
// (unless `ownTests` > 0, when the learner's stay) and `hidden` added, and
// how many cases it holds; or the tested function the code no longer has.
export function checkedProgram(code: string, own: TestBlock[], hidden: TestBlock[], ownTests: number): { source: string; cases: number } | { missing: string } {
  let lines = code.split('\n');
  if (ownTests === 0) {
    const kept: string[] = [];
    for (let i = 0; i < lines.length; ) {
      if (lines[i].trim().startsWith('#test')) {
        i = attributeEnd(lines, i);
        continue;
      }
      kept.push(lines[i]);
      i++;
    }
    lines = kept;
  }
  const add = new Map<string, string[]>();
  for (const b of [...(ownTests === 0 ? own : []), ...hidden]) add.set(b.fn, [...(add.get(b.fn) ?? []), ...b.lines]);
  let cases = 0;
  for (const [fn, cs] of add) {
    const at = lines.findIndex((l) => FUN.exec(l)?.[2] === fn);
    if (at < 0) return { missing: fn };
    const indent = FUN.exec(lines[at])![1];
    lines.splice(at, 0, ...cs.map((c) => c.split('\n').map((l, k) => (k === 0 ? indent + l : l)).join('\n')));
    cases += cs.length;
  }
  if (ownTests > 0) cases += countCases(code);
  return { source: lines.join('\n'), cases };
}

function countCases(code: string): number {
  return code.split('\n').filter((l) => l.trim().startsWith('#test')).length;
}
