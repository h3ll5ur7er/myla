import { ChangeDetectionStrategy, Component, DestroyRef, effect, inject, input, signal } from '@angular/core';
import { ActivatedRoute, RouterLink, RouterLinkActive } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { TocEntry } from '../core/content.types';

export interface NavGroup {
  title: string;
  links: { label: string; route: string; badge?: string }[];
}

// The docs' and the reference's frame: the pages on the left, the page, its
// contents on the right (the section in view marked), and the scroll to an
// anchor once the content is there.
@Component({
  selector: 'app-doc-layout',
  imports: [RouterLink, RouterLinkActive],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="layout">
      <aside class="side" [class.open]="navOpen()">
        <button class="side-toggle" type="button" (click)="navOpen.set(!navOpen())" [attr.aria-expanded]="navOpen()">
          {{ navOpen() ? 'Close' : 'Pages' }}
        </button>
        <nav aria-label="Pages">
          @for (g of nav(); track g.title) {
            <div class="group">
              <h4>{{ g.title }}</h4>
              @for (l of g.links; track l.route) {
                <a [routerLink]="l.route" routerLinkActive="active" [routerLinkActiveOptions]="{ exact: true }" (click)="navOpen.set(false)">
                  <span>{{ l.label }}</span>
                  @if (l.badge) {
                    <span class="badge">{{ l.badge }}</span>
                  }
                </a>
              }
            </div>
          }
        </nav>
      </aside>
      <article class="page">
        <ng-content />
      </article>
      <aside class="toc">
        @if (toc().length) {
          <h4>On this page</h4>
          <nav aria-label="On this page">
            @for (t of toc(); track t.id) {
              <a [routerLink]="[]" [fragment]="t.id" [class.sub]="t.level > 2" [class.active]="t.id === current()" (click)="jump($event, t.id)">{{ t.text }}</a>
            }
          </nav>
        }
        <ng-content select="[toc-extra]" />
      </aside>
    </div>
  `,
  styleUrl: './doc-layout.component.scss',
})
export class DocLayoutComponent {
  readonly nav = input<NavGroup[]>([]);
  readonly toc = input<TocEntry[]>([]);
  // true once the page's content is in the DOM
  readonly ready = input(false);
  readonly navOpen = signal(false);
  readonly current = signal<string | null>(null);
  private readonly fragment = toSignal(inject(ActivatedRoute).fragment);
  private observer: IntersectionObserver | null = null;

  constructor() {
    effect(() => {
      const f = this.fragment();
      if (this.ready() && f) {
        requestAnimationFrame(() => document.getElementById(f)?.scrollIntoView({ block: 'start' }));
      }
    });
    effect(() => {
      const toc = this.toc();
      if (!this.ready()) return;
      this.observer?.disconnect();
      const visible = new Set<string>();
      this.observer = new IntersectionObserver(
        (entries) => {
          for (const e of entries) {
            if (e.isIntersecting) visible.add(e.target.id);
            else visible.delete(e.target.id);
          }
          const first = toc.find((t) => visible.has(t.id));
          if (first) this.current.set(first.id);
        },
        { rootMargin: '-80px 0px -60% 0px' },
      );
      requestAnimationFrame(() => {
        for (const t of toc) {
          const el = document.getElementById(t.id);
          if (el) this.observer?.observe(el);
        }
      });
    });
    inject(DestroyRef).onDestroy(() => this.observer?.disconnect());
  }

  jump(e: MouseEvent, id: string): void {
    e.preventDefault();
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    history.replaceState(history.state, '', `${location.pathname}#${id}`);
    this.current.set(id);
  }
}
