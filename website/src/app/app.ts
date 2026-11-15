import { ChangeDetectionStrategy, Component, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { HeaderComponent } from './shell/header.component';
import { FooterComponent } from './shell/footer.component';
import { SearchPaletteComponent } from './shell/search-palette.component';
import { ToastsComponent } from './shell/toasts.component';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, HeaderComponent, FooterComponent, SearchPaletteComponent, ToastsComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <a class="skip" href="#main">Skip to the content</a>
    <app-header (search)="searching.set(true)" />
    <main id="main" tabindex="-1"><router-outlet /></main>
    <app-footer />
    <app-search-palette [(open)]="searching" />
    <app-toasts />
  `,
  styles: `
    :host {
      display: flex;
      flex-direction: column;
      min-height: 100vh;
    }
    main {
      flex: 1;
      outline: none;
    }
    .skip {
      position: absolute;
      left: 12px;
      top: -48px;
      z-index: 100;
      padding: 8px 14px;
      border-radius: 8px;
      background: var(--bg-raised);
      &:focus {
        top: 12px;
      }
    }
  `,
})
export class App {
  readonly searching = signal(false);
}
