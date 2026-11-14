import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { footerLine } from '../core/lore';

@Component({
  selector: 'app-footer',
  imports: [RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <footer class="footer">
      <div class="container cols">
        <div class="about">
          <a class="brand" routerLink="/"><img src="favicon.svg" alt="" width="26" height="26" /> Myla</a>
          <p>A small, statically typed language with value semantics, whose compiler is written in Myla and compiles itself.</p>
          <p class="quip">{{ line }}</p>
        </div>
        <div>
          <h3>Learn</h3>
          <a routerLink="/quickstart">Quickstart</a>
          <a routerLink="/learn">The course</a>
          <a routerLink="/playground">Playground</a>
        </div>
        <div>
          <h3>Docs</h3>
          <a routerLink="/docs">Language</a>
          <a routerLink="/reference">Standard library</a>
          <a routerLink="/reference/builtins">Builtins</a>
        </div>
        <div>
          <h3>Project</h3>
          <a href="https://github.com/h3ll5ur7er/myla" target="_blank" rel="noopener">GitHub</a>
          <a routerLink="/download">Download</a>
          <a href="https://github.com/h3ll5ur7er/myla/blob/master/docs/Project/Decisions.md" target="_blank" rel="noopener">Decisions</a>
        </div>
      </div>
      <div class="container fine">
        <span>Made with Myla, Angular and an unreasonable number of references.</span>
        <span>Mostly harmless.</span>
      </div>
    </footer>
  `,
  styles: `
    .footer {
      margin-top: 96px;
      border-top: 1px solid var(--border);
      background: var(--bg-sunken);
      padding: 56px 0 28px;
      font-size: 0.9rem;
    }
    .cols {
      display: grid;
      grid-template-columns: 2fr 1fr 1fr 1fr;
      gap: 32px;
    }
    .brand {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font: 700 1.1rem var(--font-display);
      color: var(--text);
    }
    .about p {
      color: var(--text-muted);
      max-width: 360px;
    }
    .quip {
      font-style: italic;
      color: var(--text-faint) !important;
    }
    h3 {
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: var(--text-faint);
      margin-bottom: 12px;
    }
    .cols a:not(.brand) {
      display: block;
      color: var(--text-muted);
      padding: 3px 0;
      &:hover {
        color: var(--text);
      }
    }
    .fine {
      display: flex;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 40px;
      padding-top: 20px;
      border-top: 1px solid var(--border);
      color: var(--text-faint);
      font-size: 0.8rem;
    }
    @media (max-width: 760px) {
      .cols {
        grid-template-columns: 1fr 1fr;
      }
      .about {
        grid-column: 1 / -1;
      }
    }
  `,
})
export class FooterComponent {
  readonly line = footerLine();
}
