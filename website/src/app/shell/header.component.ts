import { ChangeDetectionStrategy, Component, inject, output, signal } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { ThemeService } from '../core/theme.service';
import { ProgressService } from '../core/progress.service';

@Component({
  selector: 'app-header',
  imports: [RouterLink, RouterLinkActive],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <header class="header">
      <div class="inner">
        <a class="brand" routerLink="/" aria-label="Myla home" (click)="menu.set(false)">
          <img src="favicon.svg" alt="" width="30" height="30" />
          <span>Myla</span>
        </a>
        <nav class="nav" [class.open]="menu()" aria-label="Main">
          @for (l of links; track l.path) {
            <a [routerLink]="l.path" routerLinkActive="active" (click)="menu.set(false)">{{ l.label }}</a>
          }
        </nav>
        <div class="actions">
          <button class="search" type="button" (click)="search.emit()" aria-label="Search (Ctrl+K)">
            <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" stroke-width="2" /><path d="m20 20-3.5-3.5" stroke="currentColor" stroke-width="2" stroke-linecap="round" /></svg>
            <span class="label">Search</span><kbd>Ctrl K</kbd>
          </button>
          @if (progress.xp() > 0) {
            <a class="xp" routerLink="/learn/profile" [title]="progress.level().level.title + ', ' + progress.xp() + ' XP'">
              <span class="lvl">Lv {{ progress.level().level.n }}</span>
              <span class="bar"><i [style.width.%]="progress.level().fraction * 100"></i></span>
              @if (progress.streak().current > 0) {
                <span class="streak" aria-label="streak">🔥{{ progress.streak().current }}</span>
              }
            </a>
          }
          <button class="icon" type="button" (click)="theme.toggle()" [attr.aria-label]="theme.theme() === 'dark' ? 'Light theme' : 'Dark theme'">
            @if (theme.theme() === 'dark') {
              <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><circle cx="12" cy="12" r="4.5" fill="currentColor" /><g stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></g></svg>
            } @else {
              <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5Z" fill="currentColor" /></svg>
            }
          </button>
          <a class="icon" href="https://github.com/h3ll5ur7er/myla" target="_blank" rel="noopener" aria-label="Myla on GitHub">
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path fill="currentColor" d="M12 .5a11.5 11.5 0 0 0-3.6 22.4c.6.1.8-.3.8-.6v-2c-3.2.7-3.9-1.5-3.9-1.5-.5-1.3-1.3-1.7-1.3-1.7-1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.8 1.3 3.5 1 .1-.8.4-1.3.7-1.6-2.6-.3-5.3-1.3-5.3-5.7 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.2 1.2a11 11 0 0 1 5.8 0C17.3 4.4 18.3 4.7 18.3 4.7c.6 1.6.2 2.8.1 3.1.8.8 1.2 1.8 1.2 3.1 0 4.4-2.7 5.4-5.3 5.7.4.4.8 1.1.8 2.2v3.3c0 .3.2.7.8.6A11.5 11.5 0 0 0 12 .5Z" /></svg>
          </a>
          <button class="icon burger" type="button" (click)="menu.set(!menu())" [attr.aria-expanded]="menu()" aria-label="Menu">
            <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" stroke-width="2" stroke-linecap="round" /></svg>
          </button>
        </div>
      </div>
    </header>
  `,
  styleUrl: './header.component.scss',
})
export class HeaderComponent {
  readonly theme = inject(ThemeService);
  readonly progress = inject(ProgressService);
  readonly search = output<void>();
  readonly menu = signal(false);
  readonly links = [
    { path: '/quickstart', label: 'Quickstart' },
    { path: '/docs', label: 'Docs' },
    { path: '/reference', label: 'Reference' },
    { path: '/learn', label: 'Learn' },
    { path: '/playground', label: 'Playground' },
    { path: '/download', label: 'Download' },
  ];
}
