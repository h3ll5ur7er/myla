import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { NOT_FOUND } from '../../core/lore';

@Component({
  selector: 'app-not-found',
  imports: [RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="container lost">
      <div class="code">404</div>
      <h1>{{ q.quote }}</h1>
      <p class="who">— {{ q.who }}</p>
      <div class="ctas">
        <a class="btn primary" routerLink="/">Back to safety</a>
        <a class="btn" routerLink="/docs">The docs</a>
      </div>
      <p class="tip">Looking for something? Press <kbd>Ctrl</kbd> <kbd>K</kbd>.</p>
    </div>
  `,
  styles: `
    .lost { text-align: center; padding: 96px 0 40px; }
    .code { font: 800 clamp(6rem, 20vw, 11rem)/1 var(--font-display); background: var(--gradient); -webkit-background-clip: text; background-clip: text; color: transparent; letter-spacing: -0.05em; }
    h1 { font-size: clamp(1.3rem, 3vw, 1.9rem); max-width: 720px; margin: 20px auto 8px; }
    .who { color: var(--text-faint); margin: 0 0 32px; }
    .ctas { display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; }
    .tip { margin-top: 28px; color: var(--text-faint); font-size: 0.9rem; }
  `,
})
export class NotFoundPage {
  readonly q = NOT_FOUND[Math.floor(Math.random() * NOT_FOUND.length)];
}
