import { ChangeDetectionStrategy, Component, computed, effect, inject, resource, signal, viewChild } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { ContentService } from '../../core/content.service';
import { EditorComponent, decodeCode, encodeCode } from '../../editor/editor.component';
import { ProgressService } from '../../core/progress.service';
import { loadText, saveText } from '../../core/storage';
import { RunResult } from '../../core/toolchain.service';

const START = `// Welcome to the playground. This program is yours: edit it, run it
// (Ctrl+Enter), share it (the link holds the code). Pick an example above.

struct Planet {
    name: str,
    moons: int,
}

fun main() {
    let planets = [
        Planet { name: "Earth", moons: 1 },
        Planet { name: "Mars", moons: 2 },
        Planet { name: "Magrathea", moons: 0 },  // custom-built, moons extra
    ]
    for p in planets {
        print(f"{p.name}: {p.moons} moon{if p.moons == 1 { "" } else { "s" }}")
    }
    let total = planets.fold(0, (n: int, p: Planet) => n + p.moons)
    print(f"{total} moons in all. Mostly harmless.")
}
`;

// The playground (MYLA-633): one big editor, the repository's examples, the
// code in the URL to share, standard input, the draft kept in the browser.
@Component({
  selector: 'app-playground',
  imports: [EditorComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="pg">
      <div class="top">
        <h1>Playground</h1>
        <label class="pick">
          <span class="visually-hidden">Example</span>
          <select (change)="pick($any($event.target).value)" [value]="picked()">
            <option value="">Your program</option>
            @for (e of examples.value() ?? []; track e.file) {
              <option [value]="e.file">{{ e.title }}</option>
            }
          </select>
        </label>
        <span class="about">{{ about() }}</span>
        <span class="spacer"></span>
        <button class="btn small" type="button" (click)="stdinOpen.set(!stdinOpen())">{{ stdinOpen() ? 'Hide input' : 'Standard input' }}</button>
        <button class="btn small primary" type="button" (click)="share()">{{ shared() ? 'Link copied!' : 'Share' }}</button>
      </div>
      @if (stdinOpen()) {
        <textarea class="stdin" [value]="stdin()" (input)="stdin.set($any($event.target).value)" placeholder="What the program reads from standard input" aria-label="Standard input"></textarea>
      }
      <div class="editor-wrap">
        @if (code(); as c) {
          <myla-editor [code]="c" height="fill" label="main.my" [showOpen]="false" [stdin]="stdin()" (codeChange)="changed($event)" (ran)="ran($event)" />
        }
      </div>
    </div>
  `,
  styleUrl: './playground.page.scss',
})
export class PlaygroundPage {
  private readonly content = inject(ContentService);
  private readonly router = inject(Router);
  private readonly progress = inject(ProgressService);
  private readonly fragment = toSignal(inject(ActivatedRoute).fragment);
  private readonly editor = viewChild(EditorComponent);
  readonly examples = resource({ loader: () => this.content.playground() });
  readonly code = signal<string | null>(null);
  readonly picked = signal('');
  readonly stdin = signal('');
  readonly stdinOpen = signal(false);
  readonly shared = signal(false);
  private latest = '';
  readonly about = computed(() => this.examples.value()?.find((e) => e.file === this.picked())?.about ?? '');

  constructor() {
    effect(() => {
      if (this.code() !== null) return;
      const f = this.fragment();
      const fromUrl = f?.startsWith('code=') ? decodeCode(f.slice(5)) : null;
      const c = fromUrl ?? loadText('myla.playground') ?? START;
      this.latest = c;
      this.code.set(c);
    });
  }

  pick(file: string): void {
    this.picked.set(file);
    const e = this.examples.value()?.find((x) => x.file === file);
    const c = e ? e.source : (loadText('myla.playground') ?? START);
    this.latest = c;
    this.editor()?.setCode(c);
  }

  changed(c: string): void {
    this.latest = c;
    if (!this.picked()) saveText('myla.playground', c);
  }

  ran(_: RunResult): void {
    if (!this.picked() && this.latest !== START) this.progress.playgroundRun();
  }

  async share(): Promise<void> {
    const url = new URL(location.href);
    url.hash = `code=${encodeCode(this.latest)}`;
    history.replaceState(history.state, '', url);
    try {
      await navigator.clipboard.writeText(url.href);
      this.shared.set(true);
      setTimeout(() => this.shared.set(false), 1800);
    } catch {
      /* the address bar has it */
    }
  }
}
