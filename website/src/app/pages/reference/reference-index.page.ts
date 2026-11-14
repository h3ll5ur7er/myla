import { ChangeDetectionStrategy, Component, computed, inject, resource } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ContentService } from '../../core/content.service';
import { DocContentComponent } from '../../content/doc-content.component';
import { DocLayoutComponent } from '../../content/doc-layout.component';
import { referenceNav } from './nav';

// The reference's front page: the modules by group, then the wiki's
// overview of the standard library (MYLA-632).
@Component({
  selector: 'app-reference-index',
  imports: [DocLayoutComponent, DocContentComponent, RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <app-doc-layout [nav]="nav()" [toc]="lib.value()?.toc ?? []" [ready]="!!lib.value()">
      <span class="eyebrow">Reference</span>
      <h1 class="title">The standard library</h1>
      <p class="lead">
        {{ site.value()?.reference?.length ?? '…' }} modules, every public function, type and method, generated from the sources by Myla's own parser.
        Batteries included; towel not included.
      </p>
      <a class="card interactive builtins" routerLink="/reference/builtins">
        <span class="big">⚙️</span>
        <span><b>Builtins</b><span>print, format, assert and the methods every string, list, map, number and Option has, without an import.</span></span>
      </a>
      @for (g of groups(); track g.title) {
        <h2 class="group">{{ g.title }}</h2>
        <div class="grid">
          @for (m of g.modules; track m.slug) {
            <a class="card interactive mod" [routerLink]="m.route">
              <span class="name">{{ m.name }}</span>
              <span class="sum">{{ m.summary }}</span>
              <span class="count">{{ m.items }} {{ m.items === 1 ? 'entry' : 'entries' }}</span>
            </a>
          }
        </div>
      }
      @if (lib.value(); as l) {
        <h2 class="group">About the standard library</h2>
        <app-doc-content [html]="l.html" [examples]="l.examples" />
      }
    </app-doc-layout>
  `,
  styleUrls: ['../page.scss', './reference.scss'],
})
export class ReferenceIndexPage {
  private readonly content = inject(ContentService);
  readonly site = resource({ loader: () => this.content.site().catch(() => null) });
  readonly lib = resource({ loader: () => this.content.library().catch(() => null) });
  readonly nav = computed(() => referenceNav(this.site.value()));
  readonly groups = computed(() => {
    const s = this.site.value();
    if (!s) return [];
    const by = new Map(s.reference.map((m) => [m.slug, m]));
    return s.groups.map((g) => ({ title: g.title, modules: g.modules.map((n) => by.get(n)!).filter(Boolean) }));
  });
}
