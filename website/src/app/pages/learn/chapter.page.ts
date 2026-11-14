import { ChangeDetectionStrategy, Component, computed, effect, inject, input, resource } from '@angular/core';
import { Title } from '@angular/platform-browser';
import { RouterLink } from '@angular/router';
import { ContentService } from '../../core/content.service';
import { ProgressService } from '../../core/progress.service';
import { chapterUnlocked, exerciseUnlocked, key } from '../../core/gamification';
import { DocContentComponent } from '../../content/doc-content.component';

@Component({
  selector: 'app-chapter',
  imports: [RouterLink, DocContentComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="container narrow">
      @if (view(); as v) {
        <div class="crumbs"><a routerLink="/learn">Learn</a><span>/</span><span>Chapter {{ v.index + 1 }}</span></div>
        <header class="chapter-head">
          <span class="big" aria-hidden="true">{{ v.chapter.emoji }}</span>
          <div>
            <h1>{{ v.chapter.title }}</h1>
            <p class="lead">{{ v.chapter.tagline }}</p>
          </div>
        </header>
        @if (!v.unlocked) {
          <div class="card locked-note">🔒 This chapter opens once you've solved most of the one before. Or, if you know what you're doing, turn on <a routerLink="/learn/profile">sudo mode</a>.</div>
        }
        <app-doc-content [html]="v.chapter.intro" />
        <ol class="exercises">
          @for (e of v.exercises; track e.ex.id; let i = $index) {
            <li>
              @if (e.open) {
                <a class="card interactive ex" [class.solved]="e.solved" [class.boss]="e.ex.boss" [routerLink]="['/learn', v.chapter.id, e.ex.id]">
                  <span class="mark" aria-hidden="true">{{ e.solved ? '✓' : e.ex.boss ? '⚔️' : i + 1 }}</span>
                  <span class="t">{{ e.ex.title }}@if (e.ex.boss) {<span class="chip boss-chip">boss</span>}</span>
                  <span class="xp">{{ e.ex.xp }} XP</span>
                </a>
              } @else {
                <div class="card ex locked">
                  <span class="mark" aria-hidden="true">🔒</span>
                  <span class="t">{{ e.ex.title }}@if (e.ex.boss) {<span class="chip boss-chip">boss</span>}</span>
                  <span class="xp">{{ e.ex.boss ? 'beat the rest first' : 'locked' }}</span>
                </div>
              }
            </li>
          }
        </ol>
      } @else if (course.error()) {
        <p>The course couldn't be loaded.</p>
      } @else if (course.value()) {
        <h1>No such chapter</h1>
        <p><a routerLink="/learn">Back to the map</a></p>
      }
    </div>
  `,
  styleUrl: './learn.scss',
})
export class ChapterPage {
  readonly chapter = input.required<string>();
  private readonly content = inject(ContentService);
  private readonly progress = inject(ProgressService);
  readonly course = resource({ loader: () => this.content.course() });
  readonly view = computed(() => {
    const c = this.course.value();
    if (!c) return null;
    const index = c.chapters.findIndex((ch) => ch.id === this.chapter());
    if (index < 0) return null;
    const p = this.progress.progress();
    const chapter = c.chapters[index];
    return {
      index,
      chapter,
      unlocked: chapterUnlocked(p, c, index),
      exercises: chapter.exercises.map((ex, ei) => ({ ex, solved: !!p.solved[key(chapter.id, ex.id)], open: exerciseUnlocked(p, c, index, ei) })),
    };
  });

  constructor() {
    const title = inject(Title);
    effect(() => {
      const v = this.view();
      if (v) title.setTitle(`${v.chapter.title} · Learn Myla`);
    });
  }
}
