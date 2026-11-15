import { ChangeDetectionStrategy, Component, computed, ElementRef, inject, model, signal, viewChild, effect } from '@angular/core';
import { Router } from '@angular/router';
import { ContentService } from '../core/content.service';
import { SearchEntry } from '../core/content.types';
import { search } from '../core/search';

// Ctrl+K: the docs, the reference and the course in one search (MYLA-630).
@Component({
  selector: 'app-search-palette',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (open()) {
      <div class="backdrop" (click)="close()"></div>
      <div class="palette" role="dialog" aria-modal="true" aria-label="Search">
        <div class="field">
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" stroke-width="2" /><path d="m20 20-3.5-3.5" stroke="currentColor" stroke-width="2" stroke-linecap="round" /></svg>
          <input
            #box
            type="search"
            placeholder="Search docs, std, exercises… (try “split”, “Vec3” or “towel”)"
            [value]="query()"
            (input)="query.set(box.value); active.set(0)"
            (keydown)="key($event)"
            aria-label="Search"
            autocomplete="off"
            spellcheck="false"
          />
          <kbd>Esc</kbd>
        </div>
        <ul class="results" role="listbox">
          @for (r of results(); track r.u + r.t; let i = $index) {
            <li role="option" [attr.aria-selected]="i === active()" [class.active]="i === active()" (mousemove)="active.set(i)" (click)="go(r)">
              <span class="kind" [attr.data-k]="r.k">{{ r.k }}</span>
              <span class="t">{{ r.t }}</span>
              <span class="d">{{ r.d }}</span>
            </li>
          } @empty {
            <li class="empty">
              @if (!entries()) {
                Loading the index…
              } @else if (query().trim()) {
                Nothing found. Not even a Babel fish could translate that.
              } @else {
                Type to search {{ entries()!.length }} pages, functions, types and exercises.
              }
            </li>
          }
        </ul>
      </div>
    }
  `,
  styleUrl: './search-palette.component.scss',
  host: { '(document:keydown)': 'global($event)' },
})
export class SearchPaletteComponent {
  readonly open = model(false);
  readonly query = signal('');
  readonly active = signal(0);
  readonly entries = signal<SearchEntry[] | null>(null);
  readonly results = computed(() => {
    const e = this.entries();
    return e && this.query().trim() ? search(e, this.query(), 30) : [];
  });
  private readonly box = viewChild<ElementRef<HTMLInputElement>>('box');
  private readonly content = inject(ContentService);
  private readonly router = inject(Router);

  constructor() {
    effect(() => {
      if (this.open()) {
        if (!this.entries()) void this.content.search().then((e) => this.entries.set(e));
        queueMicrotask(() => this.box()?.nativeElement.focus());
      }
    });
  }

  global(e: KeyboardEvent): void {
    const target = e.target as HTMLElement;
    const typing = target.closest('input, textarea, [contenteditable], .cm-editor');
    if ((e.key === 'k' || e.key === 'K') && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      this.open.set(!this.open());
    } else if (e.key === '/' && !typing && !this.open()) {
      e.preventDefault();
      this.open.set(true);
    }
  }

  key(e: KeyboardEvent): void {
    const n = this.results().length;
    if (e.key === 'Escape') this.close();
    else if (e.key === 'ArrowDown') {
      e.preventDefault();
      this.active.set(n ? (this.active() + 1) % n : 0);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      this.active.set(n ? (this.active() - 1 + n) % n : 0);
    } else if (e.key === 'Enter') {
      const r = this.results()[this.active()];
      if (r) this.go(r);
    }
  }

  go(r: SearchEntry): void {
    const [path, fragment] = r.u.split('#');
    this.close();
    void this.router.navigate([path], { fragment: fragment || undefined });
  }

  close(): void {
    this.open.set(false);
    this.query.set('');
    this.active.set(0);
  }
}
