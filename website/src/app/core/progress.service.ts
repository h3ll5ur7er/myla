import { computed, Injectable, signal } from '@angular/core';
import { Course, Exercise } from './content.types';
import {
  Achievement,
  dayOf,
  emptyProgress,
  key,
  levelOf,
  levelProgress,
  newAchievements,
  Progress,
  reward,
  streaks,
  totalXp,
} from './gamification';
import { load, save } from './storage';
import { ToastService } from './toast.service';
import { confetti } from './celebrate';

const STORE = 'myla.progress.v1';

export interface SolveOutcome {
  xp: number;
  first: boolean;
  levelUp: boolean;
  achievements: Achievement[];
}

// The learner's progress (MYLA-634): kept in this browser only, as the site
// has no backend (D208); exported and imported as a file.
@Injectable({ providedIn: 'root' })
export class ProgressService {
  private readonly state = signal<Progress>(this.restore());
  private opened = new Map<string, number>();

  readonly progress = this.state.asReadonly();
  readonly xp = computed(() => totalXp(this.state()));
  readonly level = computed(() => levelProgress(this.xp()));
  readonly solvedCount = computed(() => Object.keys(this.state().solved).length);
  readonly streak = computed(() => streaks(this.state().days, Date.now()));

  constructor(private toasts: ToastService) {}

  private restore(): Progress {
    const p = load<Progress | null>(STORE, null);
    return p && p.version === 1 ? { ...emptyProgress(), ...p } : emptyProgress();
  }

  private commit(p: Progress): void {
    this.state.set(p);
    save(STORE, p);
  }

  private update(f: (p: Progress) => void): Progress {
    const p = structuredClone(this.state());
    f(p);
    this.commit(p);
    return p;
  }

  isSolved(chapter: string, exercise: string): boolean {
    return !!this.state().solved[key(chapter, exercise)];
  }

  markOpened(chapter: string, exercise: string): void {
    this.opened.set(key(chapter, exercise), Date.now());
  }

  draft(chapter: string, exercise: string): string | null {
    return this.state().drafts[key(chapter, exercise)] ?? null;
  }

  saveDraft(chapter: string, exercise: string, code: string): void {
    const k = key(chapter, exercise);
    if (this.state().drafts[k] === code) return;
    this.update((p) => {
      p.drafts[k] = code;
    });
  }

  clearDraft(chapter: string, exercise: string): void {
    this.update((p) => {
      delete p.drafts[key(chapter, exercise)];
    });
  }

  hintsShown(chapter: string, exercise: string): number {
    return this.state().hints[key(chapter, exercise)] ?? 0;
  }

  showHint(chapter: string, exercise: string): void {
    this.update((p) => {
      const k = key(chapter, exercise);
      p.hints[k] = (p.hints[k] ?? 0) + 1;
    });
    this.award(null, null);
  }

  revealSolution(chapter: string, exercise: string): void {
    this.update((p) => {
      p.revealed[key(chapter, exercise)] = true;
    });
  }

  solutionRevealed(chapter: string, exercise: string): boolean {
    return !!this.state().revealed[key(chapter, exercise)];
  }

  failed(chapter: string, exercise: string): void {
    this.update((p) => {
      const k = key(chapter, exercise);
      p.attempts[k] = (p.attempts[k] ?? 0) + 1;
    });
  }

  playgroundRun(): void {
    this.update((p) => {
      p.playgroundRuns += 1;
    });
    this.award(null, null);
  }

  setSudo(on: boolean): void {
    this.update((p) => {
      p.sudo = on;
    });
  }

  // Record a solve: what it earned, a new level, new achievements; and say
  // so with toasts and confetti.
  solve(course: Course, chapter: string, ex: Exercise): SolveOutcome {
    const k = key(chapter, ex.id);
    const before = this.state();
    if (before.solved[k]) return { xp: 0, first: false, levelUp: false, achievements: [] };
    const levelBefore = levelOf(totalXp(before)).n;
    const now = Date.now();
    const hints = before.hints[k] ?? 0;
    const withSolution = !!before.revealed[k];
    const xp = reward(ex.xp, hints, withSolution);
    const openedAt = this.opened.get(k);
    this.update((p) => {
      p.solved[k] = { at: now, xp, hints, attempts: p.attempts[k] ?? 0, ms: openedAt ? now - openedAt : null, withSolution };
      delete p.attempts[k];
      const d = dayOf(now);
      if (!p.days.includes(d)) p.days = [...p.days, d].sort();
    });
    const levelUp = levelOf(this.xp()).n > levelBefore;
    confetti(levelUp ? 220 : 120);
    this.toasts.show({
      icon: ex.boss ? '⚔️' : '✨',
      title: xp > 0 ? `+${xp} XP` : 'Solved',
      body: xp > 0 ? (ex.boss ? `Boss defeated: ${ex.title}` : ex.title) : 'No XP with the solution shown first, but the Babel fish forgives you.',
      tone: 'xp',
    });
    if (levelUp) {
      const l = this.level().level;
      this.toasts.show({ icon: '🚀', title: `Level ${l.n}: ${l.title}`, body: `As seen in ${l.from}.`, tone: 'level' }, 6500);
    }
    // the solve first, then what it unlocked
    const achievements = this.award(course, k);
    return { xp, first: true, levelUp, achievements };
  }

  // Unlock what the progress now earns, with a toast for each.
  private award(course: Course | null, latest: string | null): Achievement[] {
    const c = course ?? { chapters: [], totalXp: 0 };
    const got = newAchievements(this.state(), c, Date.now(), latest);
    if (!got.length) return got;
    this.update((p) => {
      for (const a of got) p.achievements[a.id] = Date.now();
    });
    for (const a of got) this.toasts.show({ icon: a.icon, title: `Achievement: ${a.title}`, body: a.description, tone: 'achievement' }, 6500);
    return got;
  }

  export(): string {
    return JSON.stringify(this.state(), null, 2);
  }

  import(text: string): boolean {
    try {
      const p = JSON.parse(text) as Progress;
      if (p.version !== 1 || typeof p.solved !== 'object') return false;
      this.commit({ ...emptyProgress(), ...p });
      return true;
    } catch {
      return false;
    }
  }

  reset(): void {
    this.commit(emptyProgress());
  }
}
