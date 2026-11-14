import { ChangeDetectionStrategy, Component, computed, inject, resource, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ContentService } from '../../core/content.service';
import { ProgressService } from '../../core/progress.service';
import { ACHIEVEMENTS, dayOf, LEVELS } from '../../core/gamification';
import { chapterViews } from './course';

// The learner's profile: level, streak, the last weeks, achievements, and
// the progress's file (export, import, reset) and sudo mode.
@Component({
  selector: 'app-profile',
  imports: [RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './profile.page.html',
  styleUrl: './learn.scss',
})
export class ProfilePage {
  private readonly content = inject(ContentService);
  readonly progress = inject(ProgressService);
  readonly course = resource({ loader: () => this.content.course().catch(() => null) });
  readonly chapters = computed(() => (this.course.value() ? chapterViews(this.course.value()!, this.progress.progress()) : []));
  readonly levels = LEVELS;
  readonly message = signal('');
  readonly confirmReset = signal(false);
  readonly earned = computed(() => Object.keys(this.progress.progress().achievements).length);
  readonly achievements = computed(() => {
    const got = this.progress.progress().achievements;
    return ACHIEVEMENTS.map((a) => ({ ...a, at: got[a.id] ?? null }));
  });
  // the last 12 weeks, a column a week, Monday first
  readonly weeks = computed(() => {
    const p = this.progress.progress();
    const counts = new Map<string, number>();
    for (const s of Object.values(p.solved)) counts.set(dayOf(s.at), (counts.get(dayOf(s.at)) ?? 0) + 1);
    const today = new Date();
    const start = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 7 * 11 - ((today.getDay() + 6) % 7), 12);
    const weeks: { day: string; n: number; future: boolean }[][] = [];
    for (let w = 0; w < 12; w++) {
      const col = [];
      for (let d = 0; d < 7; d++) {
        const date = new Date(start.getFullYear(), start.getMonth(), start.getDate() + w * 7 + d, 12);
        const day = dayOf(date.getTime());
        col.push({ day, n: counts.get(day) ?? 0, future: date.getTime() > today.getTime() });
      }
      weeks.push(col);
    }
    return weeks;
  });

  export(): void {
    const blob = new Blob([this.progress.export()], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `myla-progress-${dayOf(Date.now())}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  async import(input: HTMLInputElement): Promise<void> {
    const f = input.files?.[0];
    if (!f) return;
    const ok = this.progress.import(await f.text());
    this.message.set(ok ? 'Progress imported. Welcome back, traveller.' : "That file isn't a Myla progress file.");
    input.value = '';
  }

  reset(): void {
    this.progress.reset();
    this.confirmReset.set(false);
    this.message.set('Progress reset. A fresh start, like a newly built Earth Mk II.');
  }

  sudo(on: boolean): void {
    this.progress.setSudo(on);
  }
}
