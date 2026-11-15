import { ChangeDetectionStrategy, Component, computed, inject, resource } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ContentService } from '../../core/content.service';
import { ProgressService } from '../../core/progress.service';
import { ACHIEVEMENTS } from '../../core/gamification';
import { chapterViews, nextExercise } from './course';

// The course's map: where you are, where to go on, the chapters to unlock.
@Component({
  selector: 'app-learn-map',
  imports: [RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './learn-map.page.html',
  styleUrl: './learn.scss',
})
export class LearnMapPage {
  private readonly content = inject(ContentService);
  readonly progress = inject(ProgressService);
  readonly course = resource({ loader: () => this.content.course().catch(() => null) });
  readonly chapters = computed(() => (this.course.value() ? chapterViews(this.course.value()!, this.progress.progress()) : []));
  readonly next = computed(() => (this.course.value() ? nextExercise(this.course.value()!, this.progress.progress()) : null));
  readonly total = computed(() => this.chapters().reduce((s, c) => s + c.total, 0));
  readonly earned = computed(() => Object.keys(this.progress.progress().achievements).length);
  readonly achievements = ACHIEVEMENTS.length;

  lockReason(i: number): string {
    const prev = this.chapters()[i - 1];
    if (!prev) return '';
    const need = Math.ceil(prev.total * 0.6) - prev.solved;
    return `Solve ${need} more in “${prev.title}” to unlock`;
  }
}
