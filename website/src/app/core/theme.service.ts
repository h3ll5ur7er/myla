import { Injectable, signal } from '@angular/core';
import { loadText, saveText } from './storage';

export type Theme = 'dark' | 'light';

// The colour theme: index.html sets it before the first paint, this keeps
// it and the switch in the header.
@Injectable({ providedIn: 'root' })
export class ThemeService {
  readonly theme = signal<Theme>((document.documentElement.getAttribute('data-theme') as Theme) || 'dark');

  constructor() {
    if (!loadText('myla.theme')) {
      matchMedia('(prefers-color-scheme: light)').addEventListener?.('change', (e) => {
        if (!loadText('myla.theme')) this.apply(e.matches ? 'light' : 'dark');
      });
    }
  }

  toggle(): void {
    const next: Theme = this.theme() === 'dark' ? 'light' : 'dark';
    saveText('myla.theme', next);
    this.apply(next);
  }

  private apply(t: Theme): void {
    this.theme.set(t);
    document.documentElement.setAttribute('data-theme', t);
  }
}
