import { ChangeDetectionStrategy, Component, computed, effect, inject, input, resource, signal, untracked, viewChild } from '@angular/core';
import { Title } from '@angular/platform-browser';
import { Router, RouterLink } from '@angular/router';
import { ContentService } from '../../core/content.service';
import { ProgressService } from '../../core/progress.service';
import { exerciseUnlocked } from '../../core/gamification';
import { ToolchainService, testSummary } from '../../core/toolchain.service';
import { EditorComponent } from '../../editor/editor.component';
import { FAILED, loadingLine, pick, SOLVED } from '../../core/lore';
import { nextExercise } from './course';

type Verdict = { ok: true; line: string; xp: number } | { ok: false; line: string; detail: string };

// An exercise (MYLA-634): its instructions, hints and solution on the left,
// the program on the right; Check runs its tests (or compares its output) in
// the browser and, once they pass, records the solve.
@Component({
  selector: 'app-exercise',
  imports: [RouterLink, EditorComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './exercise.page.html',
  styleUrl: './learn.scss',
})
export class ExercisePage {
  readonly chapter = input.required<string>();
  readonly exercise = input.required<string>();
  private readonly content = inject(ContentService);
  private readonly toolchain = inject(ToolchainService);
  private readonly router = inject(Router);
  readonly progress = inject(ProgressService);
  private readonly editor = viewChild(EditorComponent);
  readonly course = resource({ loader: () => this.content.course() });
  readonly checking = signal<string | null>(null);
  readonly verdict = signal<Verdict | null>(null);
  readonly confirmSolution = signal(false);
  private code = '';

  readonly view = computed(() => {
    const c = this.course.value();
    if (!c) return null;
    const ci = c.chapters.findIndex((ch) => ch.id === this.chapter());
    if (ci < 0) return null;
    const ch = c.chapters[ci];
    const ei = ch.exercises.findIndex((e) => e.id === this.exercise());
    if (ei < 0) return null;
    return { course: c, ci, ei, chapter: ch, ex: ch.exercises[ei], prev: ch.exercises[ei - 1] ?? null, nextInChapter: ch.exercises[ei + 1] ?? null };
  });
  readonly unlocked = computed(() => {
    const v = this.view();
    return v ? exerciseUnlocked(this.progress.progress(), v.course, v.ci, v.ei) : false;
  });
  readonly solved = computed(() => {
    const v = this.view();
    return v ? this.progress.isSolved(v.chapter.id, v.ex.id) : false;
  });
  readonly hintsShown = computed(() => {
    const v = this.view();
    this.progress.progress();
    return v ? this.progress.hintsShown(v.chapter.id, v.ex.id) : 0;
  });
  readonly revealed = computed(() => {
    const v = this.view();
    this.progress.progress();
    return v ? this.progress.solutionRevealed(v.chapter.id, v.ex.id) : false;
  });
  readonly startCode = computed(() => {
    const v = this.view();
    if (!v) return '';
    return untracked(() => this.progress.draft(v.chapter.id, v.ex.id)) ?? v.ex.starter;
  });
  readonly next = computed(() => {
    const v = this.view();
    return v ? nextExercise(v.course, this.progress.progress()) : null;
  });

  constructor() {
    const title = inject(Title);
    effect(() => {
      const v = this.view();
      if (!v) return;
      title.setTitle(`${v.ex.title} · ${v.chapter.title} · Learn Myla`);
      untracked(() => {
        this.progress.markOpened(v.chapter.id, v.ex.id);
        this.verdict.set(null);
        this.confirmSolution.set(false);
        this.code = this.startCode();
      });
    });
  }

  changed(code: string): void {
    this.code = code;
    const v = this.view();
    if (v) this.progress.saveDraft(v.chapter.id, v.ex.id, code);
  }

  async check(): Promise<void> {
    const v = this.view();
    if (!v || this.checking()) return;
    this.checking.set(this.toolchain.status() === 'ready' ? 'Checking…' : loadingLine());
    this.verdict.set(null);
    try {
      const ex = v.ex;
      const r = await (ex.mode === 'test' ? this.toolchain.test(this.code) : this.toolchain.run(this.code)).result;
      let ok = false;
      let detail = '';
      if (r.timedOut) detail = 'It ran for 10 seconds without finishing. A loop that never ends?';
      else if (ex.mode === 'test') {
        const s = testSummary(r.stdout);
        ok = r.exitCode === 0 && !!s && s.total > 0 && s.passed === s.total;
        detail = s ? `${s.passed}/${s.total} tests pass.` : '';
        if (!ok) detail += '\n' + (r.stdout + r.stderr).trim();
      } else {
        ok = r.exitCode === 0 && r.stdout === ex.expected;
        if (!ok) detail = r.exitCode !== 0 ? (r.stderr || r.stdout).trim() : `It printed:\n${r.stdout || '(nothing)'}\nExpected:\n${ex.expected}`;
      }
      if (ok) {
        const outcome = this.progress.solve(v.course, v.chapter.id, ex);
        this.verdict.set({ ok: true, line: pick(SOLVED), xp: outcome.xp });
      } else {
        this.progress.failed(v.chapter.id, ex.id);
        this.verdict.set({ ok: false, line: pick(FAILED), detail: detail.trim() });
      }
    } catch (e) {
      this.verdict.set({ ok: false, line: 'Houston, we have a problem.', detail: `The toolchain couldn't start: ${(e as Error).message}` });
    } finally {
      this.checking.set(null);
    }
  }

  hint(): void {
    const v = this.view();
    if (v && this.hintsShown() < v.ex.hints.length) this.progress.showHint(v.chapter.id, v.ex.id);
  }

  showSolution(): void {
    const v = this.view();
    if (!v) return;
    if (!this.solved() && !this.revealed()) this.progress.revealSolution(v.chapter.id, v.ex.id);
    this.confirmSolution.set(false);
  }

  useSolution(): void {
    const v = this.view();
    if (v) this.editor()?.setCode(v.ex.solution);
    if (v) this.changed(v.ex.solution);
  }

  reset(): void {
    const v = this.view();
    if (!v) return;
    this.editor()?.setCode(v.ex.starter);
    this.code = v.ex.starter;
    this.progress.clearDraft(v.chapter.id, v.ex.id);
    this.verdict.set(null);
  }

  goNext(): void {
    const n = this.next();
    if (n) void this.router.navigate(['/learn', n.chapter, n.exercise]);
    else void this.router.navigate(['/learn/profile']);
  }
}
