import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { ToastService } from '../core/toast.service';

@Component({
  selector: 'app-toasts',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="toasts" aria-live="polite">
      @for (t of toasts.toasts(); track t.id) {
        <button class="toast" [class]="'toast ' + t.tone" type="button" (click)="toasts.dismiss(t.id)">
          <span class="icon" aria-hidden="true">{{ t.icon }}</span>
          <span class="text"><b>{{ t.title }}</b><span>{{ t.body }}</span></span>
        </button>
      }
    </div>
  `,
  styles: `
    .toasts {
      position: fixed;
      right: 20px;
      bottom: 20px;
      z-index: 900;
      display: flex;
      flex-direction: column;
      gap: 10px;
      max-width: min(380px, calc(100vw - 40px));
    }
    .toast {
      display: flex;
      gap: 12px;
      align-items: flex-start;
      text-align: left;
      padding: 14px 16px;
      border-radius: var(--radius);
      border: 1px solid var(--border-strong);
      background: var(--bg-raised);
      color: var(--text);
      box-shadow: var(--shadow);
      font: inherit;
      cursor: pointer;
      animation: pop 0.35s cubic-bezier(0.2, 1.4, 0.4, 1);
      &.xp { border-color: color-mix(in srgb, var(--lime) 50%, transparent); }
      &.level { border-color: var(--violet); box-shadow: var(--glow); }
      &.achievement { border-color: color-mix(in srgb, var(--amber) 55%, transparent); }
      &.error { border-color: var(--red); }
    }
    .icon { font-size: 1.6rem; line-height: 1; }
    .text { display: flex; flex-direction: column; gap: 2px; font-size: 0.88rem; }
    .text span { color: var(--text-muted); }
    @keyframes pop {
      from { transform: translateY(16px) scale(0.96); opacity: 0; }
      to { transform: none; opacity: 1; }
    }
  `,
})
export class ToastsComponent {
  readonly toasts = inject(ToastService);
}
