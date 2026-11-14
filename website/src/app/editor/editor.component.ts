import {
  afterNextRender,
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  ElementRef,
  inject,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { Router } from '@angular/router';
import { ExampleKind } from '../core/content.types';
import { CheckResult, Diagnostic, RunHandle, RunResult, testSummary, ToolchainService } from '../core/toolchain.service';
import { loadingLine } from '../core/lore';
import type { MylaView } from './codemirror';

type Shown =
  | { kind: 'run'; result: RunResult; matches: boolean | null }
  | { kind: 'test'; result: RunResult; passed: number; total: number }
  | { kind: 'check'; result: CheckResult; expectedError: boolean }
  | { kind: 'error'; message: string };

// <myla-editor>: a Myla program anyone can edit and run anywhere on the site
// (MYLA-633, D208). The code shows as text at once; CodeMirror loads when the
// editor comes near the screen, the toolchain on the first run or edit.
@Component({
  selector: 'myla-editor',
  imports: [DecimalPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './editor.component.html',
  styleUrl: './editor.component.scss',
  host: { '[class.fill]': "height() === 'fill'" },
})
export class EditorComponent {
  readonly code = input.required<string>();
  readonly kind = input<ExampleKind | 'test'>('run');
  readonly expected = input<string | null>(null);
  readonly label = input<string>('main.my');
  readonly height = input<'auto' | 'fill'>('auto');
  readonly stdin = input<string>('');
  readonly showOpen = input(true);
  readonly showRun = input(true);
  readonly codeChange = output<string>();
  readonly ran = output<RunResult>();

  private readonly toolchain = inject(ToolchainService);
  private readonly router = inject(Router);
  private readonly host = viewChild.required<ElementRef<HTMLElement>>('host');

  readonly current = signal('');
  readonly ready = signal(false);
  readonly busy = signal<string | null>(null);
  readonly shown = signal<Shown | null>(null);
  readonly copied = signal(false);
  readonly modified = computed(() => this.current() !== this.code());
  readonly hasTests = computed(() => /^\s*#test/m.test(this.current()));
  readonly hasMain = computed(() => /^\s*(async\s+)?fun\s+main\s*\(/m.test(this.current()));
  readonly lines = computed(() => this.code().replace(/\n$/, '').split('\n'));
  readonly badge = computed(() => {
    switch (this.kind()) {
      case 'fragment':
        return 'fragment';
      case 'error':
        return 'meant to fail';
      case 'check':
        return 'checks';
      case 'test':
        return 'tests';
      default:
        return this.expected() ? 'runs' : 'runs';
    }
  });

  private view: MylaView | null = null;
  private handle: RunHandle | null = null;
  private observer: IntersectionObserver | null = null;

  constructor() {
    const destroyRef = inject(DestroyRef);
    afterNextRender(() => {
      this.current.set(this.code());
      const el = this.host().nativeElement;
      if (this.height() === 'fill' || typeof IntersectionObserver === 'undefined') {
        void this.mount();
      } else {
        this.observer = new IntersectionObserver(
          (entries) => {
            if (entries.some((e) => e.isIntersecting)) {
              this.observer?.disconnect();
              void this.mount();
            }
          },
          { rootMargin: '400px' },
        );
        this.observer.observe(el);
      }
    });
    destroyRef.onDestroy(() => {
      this.observer?.disconnect();
      this.handle?.stop();
      this.view?.destroy();
    });
  }

  private async mount(): Promise<void> {
    if (this.view) return;
    const { createView } = await import('./codemirror');
    const el = this.host().nativeElement;
    el.textContent = '';
    const lint = this.kind() !== 'fragment';
    let edited = false;
    this.view = createView(
      el,
      this.current(),
      {
        onChange: (c) => {
          edited = true;
          this.current.set(c);
          this.codeChange.emit(c);
        },
        onRun: () => this.primary(),
        // the toolchain loads on the first edit, not on the page's load
        check: (c) => (edited || this.toolchain.status() === 'ready' ? this.diagnostics(c) : Promise.resolve(null)),
      },
      { editable: true, lint },
    );
    this.ready.set(true);
  }

  private async diagnostics(code: string): Promise<Diagnostic[] | null> {
    if (this.kind() === 'fragment') return null;
    try {
      return (await this.toolchain.check(code)).diagnostics;
    } catch {
      return null;
    }
  }

  // Ctrl+Enter: what the editor is for.
  primary(): void {
    if (this.kind() === 'fragment') return;
    if (this.kind() === 'error' || (this.kind() === 'check' && !this.hasTests())) void this.check();
    else if (this.kind() === 'test' || (!this.hasMain() && this.hasTests())) this.test();
    else this.run();
  }

  run(): void {
    this.exec('run');
  }

  test(): void {
    this.exec('test');
  }

  private exec(op: 'run' | 'test'): void {
    if (this.busy()) {
      this.stop();
      return;
    }
    this.busy.set(this.toolchain.status() === 'ready' ? (op === 'run' ? 'Running…' : 'Testing…') : loadingLine());
    const h = op === 'run' ? this.toolchain.run(this.current(), { stdin: this.stdin() }) : this.toolchain.test(this.current());
    this.handle = h;
    h.result.then(
      (r) => {
        if (this.handle !== h) return;
        this.handle = null;
        this.busy.set(null);
        if (op === 'run') {
          const exp = this.expected();
          const matches = exp !== null && !this.modified() && !r.timedOut && !r.stopped ? r.stdout === exp : null;
          this.shown.set({ kind: 'run', result: r, matches });
        } else {
          const s = testSummary(r.stdout) ?? { passed: 0, total: 0 };
          this.shown.set({ kind: 'test', result: r, ...s });
        }
        this.ran.emit(r);
        this.view?.relint();
      },
      (e: Error) => {
        this.handle = null;
        this.busy.set(null);
        this.shown.set({ kind: 'error', message: `The toolchain couldn't start: ${e.message}` });
      },
    );
  }

  stop(): void {
    this.handle?.stop();
  }

  async check(): Promise<void> {
    this.busy.set(this.toolchain.status() === 'ready' ? 'Checking…' : loadingLine());
    try {
      const r = await this.toolchain.check(this.current());
      this.shown.set({ kind: 'check', result: r, expectedError: this.kind() === 'error' });
      this.view?.relint();
    } catch (e) {
      this.shown.set({ kind: 'error', message: `The toolchain couldn't start: ${(e as Error).message}` });
    } finally {
      this.busy.set(null);
    }
  }

  reset(): void {
    this.view?.setCode(this.code());
    this.current.set(this.code());
    this.shown.set(null);
  }

  setCode(code: string): void {
    if (this.view) this.view.setCode(code);
    this.current.set(code);
  }

  async copy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(this.current());
      this.copied.set(true);
      setTimeout(() => this.copied.set(false), 1500);
    } catch {
      /* no clipboard: nothing to do */
    }
  }

  open(): void {
    void this.router.navigate(['/playground'], { fragment: `code=${encodeCode(this.current())}` });
  }

  closeOutput(): void {
    this.shown.set(null);
  }

  firstLines(text: string, n = 60): string {
    const lines = text.split('\n');
    return lines.length > n ? lines.slice(0, n).join('\n') + `\n… (${lines.length - n} more lines)` : text;
  }
}

// A program in a URL: UTF-8, base64url.
export function encodeCode(code: string): string {
  const bytes = new TextEncoder().encode(code);
  let bin = '';
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export function decodeCode(s: string): string | null {
  try {
    const bin = atob(s.replace(/-/g, '+').replace(/_/g, '/'));
    return new TextDecoder().decode(Uint8Array.from(bin, (c) => c.charCodeAt(0)));
  } catch {
    return null;
  }
}
