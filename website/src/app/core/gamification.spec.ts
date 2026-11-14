import { describe, expect, it } from 'vitest';
import { Course } from './content.types';
import {
  ACHIEVEMENTS,
  chapterUnlocked,
  dayOf,
  emptyProgress,
  exerciseUnlocked,
  key,
  LEVELS,
  levelOf,
  levelProgress,
  newAchievements,
  reward,
  streaks,
  totalXp,
} from './gamification';

function ex(id: string, xp = 10, boss = false) {
  return { id, file: '', title: id, xp, boss, mode: 'test' as const, expected: null, hints: [], instructions: '', starter: '', solution: '' };
}

const course: Course = {
  chapters: [
    { id: 'a', title: 'A', emoji: '', tagline: '', intro: '', exercises: [ex('1'), ex('2'), ex('3'), ex('4'), ex('boss', 50, true)] },
    { id: 'b', title: 'B', emoji: '', tagline: '', intro: '', exercises: [ex('1'), ex('2')] },
  ],
  totalXp: 110,
};

const at = (y: number, m: number, d: number, h = 12) => new Date(y, m - 1, d, h).getTime();

function solve(p: ReturnType<typeof emptyProgress>, k: string, t: number, extra: Partial<{ hints: number; attempts: number; ms: number; withSolution: boolean; xp: number }> = {}) {
  p.solved[k] = { at: t, xp: extra.xp ?? 10, hints: extra.hints ?? 0, attempts: extra.attempts ?? 0, ms: extra.ms ?? null, withSolution: extra.withSolution ?? false };
  const d = dayOf(t);
  if (!p.days.includes(d)) p.days.push(d);
}

describe('levels', () => {
  it('starts mostly harmless and ends as the pirate king', () => {
    expect(levelOf(0).title).toBe('Mostly Harmless');
    expect(levelOf(24).n).toBe(1);
    expect(levelOf(25).title).toBe('Hoopy Frood');
    expect(levelOf(1_000_000).title).toBe('Pirate King');
  });

  it('are ordered by the experience they need', () => {
    for (let i = 1; i < LEVELS.length; i++) expect(LEVELS[i].xp).toBeGreaterThan(LEVELS[i - 1].xp);
  });

  it('report the way to the next level', () => {
    const p = levelProgress(40);
    expect(p.level.n).toBe(2);
    expect(p.next?.n).toBe(3);
    expect(p.fraction).toBeCloseTo((40 - 25) / (60 - 25));
    expect(levelProgress(5000).fraction).toBe(1);
  });
});

describe('reward', () => {
  it('costs 15 % a hint, at most half, and nothing with the solution shown', () => {
    expect(reward(20, 0, false)).toBe(20);
    expect(reward(20, 1, false)).toBe(17);
    expect(reward(20, 9, false)).toBe(10);
    expect(reward(20, 0, true)).toBe(0);
  });
});

describe('streaks', () => {
  it('counts days in a row ending today or yesterday, across a month', () => {
    const days = ['2026-10-30', '2026-10-31', '2026-11-01', '2026-11-05'];
    expect(streaks(days, at(2026, 11, 1))).toEqual({ current: 3, best: 3 });
    expect(streaks(days, at(2026, 11, 2))).toEqual({ current: 3, best: 3 });
    expect(streaks(days, at(2026, 11, 3))).toEqual({ current: 0, best: 3 });
    expect(streaks(days, at(2026, 11, 5))).toEqual({ current: 1, best: 3 });
    expect(streaks([], at(2026, 11, 5))).toEqual({ current: 0, best: 0 });
  });
});

describe('unlocks', () => {
  it('open a chapter at 60 % of the one before, a boss after the rest', () => {
    const p = emptyProgress();
    expect(chapterUnlocked(p, course, 0)).toBe(true);
    expect(chapterUnlocked(p, course, 1)).toBe(false);
    solve(p, key('a', '1'), at(2026, 11, 1));
    solve(p, key('a', '2'), at(2026, 11, 1));
    expect(chapterUnlocked(p, course, 1)).toBe(false);
    solve(p, key('a', '3'), at(2026, 11, 1));
    expect(chapterUnlocked(p, course, 1)).toBe(true);
    expect(exerciseUnlocked(p, course, 0, 4)).toBe(false);
    solve(p, key('a', '4'), at(2026, 11, 1));
    expect(exerciseUnlocked(p, course, 0, 4)).toBe(true);
  });

  it('are all open in sudo mode', () => {
    const p = { ...emptyProgress(), sudo: true };
    expect(chapterUnlocked(p, course, 1)).toBe(true);
    expect(exerciseUnlocked(p, course, 0, 4)).toBe(true);
  });
});

describe('achievements', () => {
  const ids = (list: { id: string }[]) => list.map((a) => a.id).sort();

  it('have unique ids', () => {
    expect(new Set(ACHIEVEMENTS.map((a) => a.id)).size).toBe(ACHIEVEMENTS.length);
  });

  it("start with don't panic, and aren't given twice", () => {
    const p = emptyProgress();
    const now = at(2026, 11, 14, 15);
    expect(newAchievements(p, course, now, null)).toEqual([]);
    solve(p, key('a', '1'), now);
    expect(ids(newAchievements(p, course, now, key('a', '1')))).toEqual(['dont-panic']);
    p.achievements['dont-panic'] = now;
    expect(newAchievements(p, course, now, key('a', '1'))).toEqual([]);
  });

  it('see speed, persistence, the night, towel day and a boss without hints', () => {
    const p = emptyProgress();
    solve(p, key('a', '1'), at(2026, 5, 25, 3), { ms: 30_000, attempts: 6 });
    solve(p, key('a', 'boss'), at(2026, 6, 1), { xp: 50 });
    const got = ids(newAchievements(p, course, at(2026, 6, 1), key('a', 'boss')));
    expect(got).toEqual(['believe-it', 'boss-fight', 'dont-panic', 'gilfoyle', 'middle-out', 'night-owl', 'towel-day']);
  });

  it('give no speed or persistence badge for a solve with the solution shown', () => {
    const p = emptyProgress();
    solve(p, key('a', '1'), at(2026, 6, 1), { ms: 1000, attempts: 9, withSolution: true, xp: 0 });
    expect(ids(newAchievements(p, course, at(2026, 6, 1), key('a', '1')))).toEqual(['dont-panic']);
  });

  it('see a whole chapter without hints, streaks and the whole course', () => {
    const p = emptyProgress();
    const days = [at(2026, 11, 10), at(2026, 11, 11), at(2026, 11, 12)];
    ['1', '2', '3', '4', 'boss'].forEach((e, i) => solve(p, key('a', e), days[Math.min(i, 2)]));
    solve(p, key('b', '1'), days[2]);
    solve(p, key('b', '2'), days[2]);
    const got = ids(newAchievements(p, course, days[2], key('b', '2')));
    expect(got).toContain('babel-fish');
    expect(got).toContain('gum-gum');
    expect(got).toContain('thanks-for-the-fish');
    expect(got).not.toContain('infinity-gauntlet');
    expect(totalXp(p)).toBe(70);
  });
});
