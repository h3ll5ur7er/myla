import {
  ApplicationRef,
  ChangeDetectionStrategy,
  Component,
  ComponentRef,
  createComponent,
  DestroyRef,
  effect,
  ElementRef,
  EnvironmentInjector,
  inject,
  input,
} from '@angular/core';
import { Router } from '@angular/router';
import { EditorComponent } from '../editor/editor.component';
import { Example } from '../core/content.types';

// A converted wiki page (MYLA-631): its HTML, with a <myla-editor> in each
// example's placeholder, and its links routed in the app (D208).
@Component({
  selector: 'app-doc-content',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: '',
  host: { class: 'prose', '(click)': 'onClick($event)' },
})
export class DocContentComponent {
  readonly html = input.required<string>();
  readonly examples = input<Example[]>([]);

  private readonly el = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly router = inject(Router);
  private readonly appRef = inject(ApplicationRef);
  private readonly injector = inject(EnvironmentInjector);
  private editors: ComponentRef<EditorComponent>[] = [];

  constructor() {
    effect(() => this.render(this.html(), this.examples()));
    inject(DestroyRef).onDestroy(() => this.clear());
  }

  private clear(): void {
    for (const e of this.editors) {
      this.appRef.detachView(e.hostView);
      e.destroy();
    }
    this.editors = [];
  }

  private render(html: string, examples: Example[]): void {
    this.clear();
    const root = this.el.nativeElement;
    root.innerHTML = html;
    const base = basePath();
    for (const a of Array.from(root.querySelectorAll<HTMLAnchorElement>('a[href]'))) {
      const href = a.getAttribute('href')!;
      if (href.startsWith('/')) {
        a.dataset['route'] = href;
        a.setAttribute('href', base + href.slice(1));
      } else if (href.startsWith('#')) {
        a.dataset['hash'] = href.slice(1);
        a.setAttribute('href', location.pathname + href);
      }
    }
    for (const slot of Array.from(root.querySelectorAll<HTMLElement>('.myla-example'))) {
      const ex = examples[Number(slot.dataset['i'])];
      if (!ex) continue;
      const ref = createComponent(EditorComponent, { environmentInjector: this.injector, hostElement: slot });
      ref.setInput('code', ex.source);
      ref.setInput('kind', ex.kind);
      ref.setInput('expected', ex.output);
      this.appRef.attachView(ref.hostView);
      this.editors.push(ref);
    }
  }

  onClick(event: MouseEvent): void {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const a = (event.target as HTMLElement).closest('a');
    if (!a) return;
    const route = a.dataset['route'];
    const hash = a.dataset['hash'];
    if (route) {
      event.preventDefault();
      void this.router.navigateByUrl(route);
    } else if (hash !== undefined) {
      event.preventDefault();
      document.getElementById(hash)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      history.replaceState(history.state, '', `${location.pathname}#${hash}`);
    }
  }
}

// The path of the document's base, ending with `/`: `/` or `/myla/`.
export function basePath(): string {
  const p = new URL(document.baseURI).pathname;
  return p.endsWith('/') ? p : p + '/';
}
