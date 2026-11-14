import { SearchEntry } from './content.types';

// How well `entry` matches the query (higher is better, 0 none): the title
// first (exact, prefix, a word's start, inside, its letters in order), then
// the detail line.
export function score(entry: SearchEntry, query: string): number {
  const q = query.trim().toLowerCase();
  if (!q) return 0;
  const t = entry.t.toLowerCase();
  let s = 0;
  if (t === q) s = 100;
  else if (t.startsWith(q)) s = 80 - Math.min(20, t.length - q.length);
  else if (new RegExp(`(^|[._\\s-])${escapeRe(q)}`).test(t)) s = 60;
  else if (t.includes(q)) s = 45;
  else if (subsequence(q, t)) s = 20;
  else if (entry.d.toLowerCase().includes(q)) s = 12;
  if (!s) return 0;
  // modules and pages before their members, at equal scores
  const bonus: Record<string, number> = { Module: 6, Docs: 4, Learn: 3, Reference: 5 };
  return s + (bonus[entry.k] ?? 0);
}

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function subsequence(q: string, t: string): boolean {
  let i = 0;
  for (const c of t) if (c === q[i]) i++;
  return i === q.length && q.length >= 3;
}

export function search(entries: SearchEntry[], query: string, limit = 40): SearchEntry[] {
  return entries
    .map((e) => ({ e, s: score(e, query) }))
    .filter((x) => x.s > 0)
    .sort((a, b) => b.s - a.s || a.e.t.length - b.e.t.length)
    .slice(0, limit)
    .map((x) => x.e);
}
