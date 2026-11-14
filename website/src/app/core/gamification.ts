// The learn area's rules (MYLA-634, D208): experience, levels, streaks,
// achievements and unlocks, as pure functions of the learner's progress, so
// they are tested on their own (gamification.spec.ts).

import { Chapter, Course } from './content.types';

export interface Solve {
  at: number; // when, ms since the epoch
  xp: number; // what it earned
  hints: number;
  attempts: number; // failed checks before it
  ms: number | null; // from opening the exercise to solving it
  withSolution: boolean;
}

export interface Progress {
  version: 1;
  solved: Record<string, Solve>; // by `chapter/exercise`
  attempts: Record<string, number>; // failed checks, not yet solved
  hints: Record<string, number>; // hints shown
  revealed: Record<string, boolean>; // solution shown before solving
  drafts: Record<string, string>;
  days: string[]; // the local dates with a solve, `2026-11-14`, sorted
  achievements: Record<string, number>; // id -> when
  playgroundRuns: number;
  sudo: boolean; // every chapter unlocked
}

export function emptyProgress(): Progress {
  return { version: 1, solved: {}, attempts: {}, hints: {}, revealed: {}, drafts: {}, days: [], achievements: {}, playgroundRuns: 0, sudo: false };
}

export const key = (chapter: string, exercise: string) => `${chapter}/${exercise}`;

// --- experience and levels ----------------------------------------------------------------

export interface Level {
  n: number;
  title: string;
  from: string; // where the title comes from
  xp: number; // needed to reach it
}

export const LEVELS: Level[] = [
  { n: 1, title: 'Mostly Harmless', from: "The Hitchhiker's Guide to the Galaxy", xp: 0 },
  { n: 2, title: 'Hoopy Frood', from: "The Hitchhiker's Guide to the Galaxy", xp: 25 },
  { n: 3, title: 'Academy Student', from: 'Naruto', xp: 60 },
  { n: 4, title: 'Genin', from: 'Naruto', xp: 110 },
  { n: 5, title: 'Chūnin', from: 'Naruto', xp: 175 },
  { n: 6, title: 'Grand Line Rookie', from: 'One Piece', xp: 260 },
  { n: 7, title: 'Pied Piper Engineer', from: 'Silicon Valley', xp: 360 },
  { n: 8, title: 'Jōnin', from: 'Naruto', xp: 480 },
  { n: 9, title: 'Supernova', from: 'One Piece', xp: 620 },
  { n: 10, title: 'Avenger', from: 'Marvel', xp: 780 },
  { n: 11, title: 'Sannin', from: 'Naruto', xp: 960 },
  { n: 12, title: 'Hokage', from: 'Naruto', xp: 1160 },
  { n: 13, title: 'Pirate King', from: 'One Piece', xp: 1380 },
];

export function totalXp(p: Progress): number {
  return Object.values(p.solved).reduce((s, x) => s + x.xp, 0);
}

export function levelOf(xp: number): Level {
  let lv = LEVELS[0];
  for (const l of LEVELS) if (xp >= l.xp) lv = l;
  return lv;
}

// How far into the current level: 0..1 (1 at the top level).
export function levelProgress(xp: number): { level: Level; next: Level | null; fraction: number } {
  const level = levelOf(xp);
  const next = LEVELS.find((l) => l.n === level.n + 1) ?? null;
  const fraction = next ? (xp - level.xp) / (next.xp - level.xp) : 1;
  return { level, next, fraction };
}

// What solving earns: the exercise's xp, 15 % less for each hint (at least
// half), nothing when the solution was shown first.
export function reward(xp: number, hints: number, withSolution: boolean): number {
  if (withSolution) return 0;
  return Math.round(xp * Math.max(0.5, 1 - 0.15 * hints));
}

// --- days and streaks ------------------------------------------------------------------------

export function dayOf(t: number): string {
  const d = new Date(t);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function prevDay(day: string): string {
  const [y, m, d] = day.split('-').map(Number);
  return dayOf(new Date(y, m - 1, d - 1, 12).getTime());
}

// The current streak (days in a row with a solve, ending today or
// yesterday) and the best one.
export function streaks(days: string[], now: number): { current: number; best: number } {
  const set = new Set(days);
  let best = 0;
  for (const d of set) {
    if (set.has(prevDay(d))) continue; // not the start of a run
    let n = 0;
    let x = d;
    while (set.has(x)) {
      n++;
      const [y, m, dd] = x.split('-').map(Number);
      x = dayOf(new Date(y, m - 1, dd + 1, 12).getTime());
    }
    best = Math.max(best, n);
  }
  const today = dayOf(now);
  let end = set.has(today) ? today : set.has(prevDay(today)) ? prevDay(today) : null;
  let current = 0;
  while (end && set.has(end)) {
    current++;
    end = prevDay(end);
  }
  return { current, best };
}

// --- unlocks ------------------------------------------------------------------------------------

export function chapterSolved(p: Progress, ch: Chapter): number {
  return ch.exercises.filter((e) => p.solved[key(ch.id, e.id)]).length;
}

// A chapter opens once the one before is at least 60 % solved.
export function chapterUnlocked(p: Progress, course: Course, index: number): boolean {
  if (p.sudo || index === 0) return true;
  const prev = course.chapters[index - 1];
  return chapterSolved(p, prev) >= Math.ceil(prev.exercises.length * 0.6);
}

// A boss opens once the rest of its chapter is solved.
export function exerciseUnlocked(p: Progress, course: Course, ci: number, ei: number): boolean {
  if (!chapterUnlocked(p, course, ci)) return false;
  const ch = course.chapters[ci];
  const ex = ch.exercises[ei];
  if (!ex.boss || p.sudo) return true;
  return ch.exercises.every((e, i) => i === ei || e.boss || p.solved[key(ch.id, e.id)]);
}

// --- achievements ---------------------------------------------------------------------------

export interface Achievement {
  id: string;
  icon: string;
  title: string;
  description: string;
  // whether it is earned, given the progress after the latest solve
  earned(p: Progress, course: Course, now: number, latest: string | null): boolean;
}

const solves = (p: Progress) => Object.values(p.solved);

export const ACHIEVEMENTS: Achievement[] = [
  { id: 'dont-panic', icon: '🌌', title: "Don't Panic", description: 'Solve your first exercise.', earned: (p) => solves(p).length >= 1 },
  {
    id: 'towel',
    icon: '🧣',
    title: 'Hitchhiker',
    description: "Use your first hint. A towel is about the most massively useful thing an interstellar hitchhiker can have.",
    earned: (p) => Object.values(p.hints).some((n) => n > 0),
  },
  {
    id: 'hello-world',
    icon: '🛰️',
    title: 'Hello, Playground',
    description: 'Run a program of your own in the playground.',
    earned: (p) => p.playgroundRuns >= 1,
  },
  {
    id: 'shadow-clone',
    icon: '🍥',
    title: 'Shadow Clone Jutsu',
    description: 'Solve five exercises in one day.',
    earned: (p, _c, now) => solves(p).filter((s) => dayOf(s.at) === dayOf(now)).length >= 5,
  },
  {
    id: 'middle-out',
    icon: '📈',
    title: 'Middle-Out',
    description: 'Solve an exercise within a minute of opening it. Optimal tip-to-tip efficiency.',
    earned: (p) => solves(p).some((s) => s.ms !== null && s.ms <= 60_000 && !s.withSolution),
  },
  {
    id: 'gilfoyle',
    icon: '🤘',
    title: 'Persistence of Gilfoyle',
    description: 'Solve an exercise after five failed checks. It was never the code; it was the universe.',
    earned: (p) => solves(p).some((s) => s.attempts >= 5 && !s.withSolution),
  },
  {
    id: 'night-owl',
    icon: '🦉',
    title: 'Night Owl',
    description: 'Solve an exercise between midnight and five in the morning.',
    earned: (p) => solves(p).some((s) => new Date(s.at).getHours() < 5),
  },
  {
    id: 'towel-day',
    icon: '🐬',
    title: 'Towel Day',
    description: 'Solve an exercise on the 25th of May.',
    earned: (p) => solves(p).some((s) => {
      const d = new Date(s.at);
      return d.getMonth() === 4 && d.getDate() === 25;
    }),
  },
  {
    id: 'boss-fight',
    icon: '⚔️',
    title: 'Boss Fight',
    description: "Defeat a chapter's boss.",
    earned: (p, c) => c.chapters.some((ch) => ch.exercises.some((e) => e.boss && p.solved[key(ch.id, e.id)])),
  },
  {
    id: 'believe-it',
    icon: '🦊',
    title: 'Believe It!',
    description: 'Defeat a boss without a single hint.',
    earned: (p, c) => c.chapters.some((ch) => ch.exercises.some((e) => {
      const s = p.solved[key(ch.id, e.id)];
      return e.boss && s && s.hints === 0 && !s.withSolution;
    })),
  },
  {
    id: 'babel-fish',
    icon: '🐟',
    title: 'Babel Fish',
    description: 'Finish a whole chapter without hints: you understand everything, it just goes in your ear.',
    earned: (p, c) => c.chapters.some((ch) => ch.exercises.length > 0 && ch.exercises.every((e) => {
      const s = p.solved[key(ch.id, e.id)];
      return s && s.hints === 0 && !s.withSolution;
    })),
  },
  {
    id: 'gum-gum',
    icon: '🔥',
    title: 'Gum-Gum Streak',
    description: 'Solve something three days in a row.',
    earned: (p, _c, now) => streaks(p.days, now).best >= 3,
  },
  {
    id: 'will-of-d',
    icon: '🏴‍☠️',
    title: 'The Will of D.',
    description: 'Keep a seven-day streak. Inherited will cannot be stopped.',
    earned: (p, _c, now) => streaks(p.days, now).best >= 7,
  },
  {
    id: 'infinity-gauntlet',
    icon: '💎',
    title: 'Infinity Gauntlet',
    description: 'Complete six chapters: all six stones. Perfectly balanced, as all things should be.',
    earned: (p, c) => c.chapters.filter((ch) => ch.exercises.length > 0 && chapterSolved(p, ch) === ch.exercises.length).length >= 6,
  },
  {
    id: 'the-answer',
    icon: '4️⃣',
    title: 'The Answer',
    description: 'Solve 42 exercises. Now you only need to know the question.',
    earned: (p) => solves(p).length >= 42,
  },
  {
    id: 'thanks-for-the-fish',
    icon: '🐬',
    title: 'So Long, and Thanks for All the Fish',
    description: 'Finish the whole course.',
    earned: (p, c) => c.chapters.length > 0 && c.chapters.every((ch) => chapterSolved(p, ch) === ch.exercises.length),
  },
  {
    id: 'pirate-king',
    icon: '👑',
    title: 'King of the Pirates',
    description: 'Reach the highest level. The One Piece is real.',
    earned: (p) => levelOf(totalXp(p)).n === LEVELS[LEVELS.length - 1].n,
  },
];

// The achievements earned now that weren't before.
export function newAchievements(p: Progress, course: Course, now: number, latest: string | null): Achievement[] {
  return ACHIEVEMENTS.filter((a) => !p.achievements[a.id] && a.earned(p, course, now, latest));
}
