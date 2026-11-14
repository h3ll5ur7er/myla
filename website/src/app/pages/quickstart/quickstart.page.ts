import { ChangeDetectionStrategy, Component, inject, resource, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ContentService } from '../../core/content.service';
import { DocContentComponent } from '../../content/doc-content.component';
import { DocLayoutComponent } from '../../content/doc-layout.component';
import { EditorComponent } from '../../editor/editor.component';

// Quickstart: three steps to a toolchain, a program to try at once, then the
// wiki's Getting-started page (MYLA-630).
@Component({
  selector: 'app-quickstart',
  imports: [DocLayoutComponent, DocContentComponent, EditorComponent, RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <app-doc-layout [nav]="nav" [toc]="page.value()?.toc ?? []" [ready]="!!page.value()">
      <span class="eyebrow">Quickstart</span>
      <h1 class="title">From zero to <span class="gradient-text">Hello, Universe</span></h1>
      <p class="lead">Three commands on Linux (x86-64 or aarch64). The toolchain builds itself from a seed in about ten seconds: grab a towel, not a coffee.</p>
      <ol class="steps">
        @for (s of steps; track s.cmd; let i = $index) {
          <li class="card">
            <span class="n">{{ i + 1 }}</span>
            <div>
              <b>{{ s.title }}</b>
              <div class="cmd"><code>{{ s.cmd }}</code><button type="button" class="copy" (click)="copy(s.cmd, i)">{{ copied() === i ? 'Copied' : 'Copy' }}</button></div>
              <span class="note">{{ s.note }}</span>
            </div>
          </li>
        }
      </ol>
      <div class="try">
        <div>
          <h2>Or skip the install</h2>
          <p>Everything below runs in your browser: the checker and the interpreter are Myla, compiled to WebAssembly.</p>
          <a class="btn" routerLink="/learn">Take the course →</a>
        </div>
        <myla-editor [code]="hello" [expected]="helloOutput" label="hello.my" />
      </div>
      @if (page.value(); as p) {
        <app-doc-content [html]="p.html" [examples]="p.examples" />
      }
    </app-doc-layout>
  `,
  styleUrls: ['../page.scss', './quickstart.page.scss'],
})
export class QuickstartPage {
  private readonly content = inject(ContentService);
  readonly page = resource({ loader: () => this.content.quickstart().catch(() => null) });
  readonly copied = signal<number | null>(null);
  readonly nav = [
    { title: 'Start', links: [{ label: 'Quickstart', route: '/quickstart' }, { label: 'Download', route: '/download' }, { label: 'Playground', route: '/playground' }] },
    { title: 'Then', links: [{ label: 'The course', route: '/learn' }, { label: 'The language', route: '/docs' }, { label: 'The standard library', route: '/reference' }] },
  ];
  readonly steps = [
    { title: 'Clone the repository', cmd: 'git clone https://github.com/h3ll5ur7er/myla && cd myla', note: 'Needs git, and GNU as and ld (binutils).' },
    { title: 'Bootstrap the toolchain', cmd: 'scripts/bootstrap.sh', note: 'Builds the compiler from the seed, checks it compiles itself to a fixed point, writes build/myla.' },
    { title: 'Run a program', cmd: 'build/myla run examples/hello.my', note: 'Also: myla test, myla build, myla check, myla new.' },
  ];
  readonly helloOutput = 'Hello, Universe!\n6 x 7 = 42\n';
  readonly hello = 'fun main() {\n    let who = "Universe"\n    print(f"Hello, {who}!")\n    let (a, b) = (6, 7)\n    print(f"{a} x {b} = {a * b}")\n}\n';

  async copy(text: string, i: number): Promise<void> {
    try {
      await navigator.clipboard.writeText(text);
      this.copied.set(i);
      setTimeout(() => this.copied.set(null), 1500);
    } catch {
      /* no clipboard */
    }
  }
}
