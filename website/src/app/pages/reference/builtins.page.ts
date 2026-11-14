import { ChangeDetectionStrategy, Component, computed, inject, resource } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ContentService } from '../../core/content.service';
import { DocContentComponent } from '../../content/doc-content.component';
import { DocLayoutComponent } from '../../content/doc-layout.component';
import { referenceNav } from './nav';

// The builtins: the wiki's "Built-in functions" (Standard-library.md) and
// the implicit modules, whose methods every value of a built-in type has.
@Component({
  selector: 'app-builtins-page',
  imports: [DocLayoutComponent, DocContentComponent, RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <app-doc-layout [nav]="nav()" [toc]="[]" [ready]="!!section()">
      <div class="crumbs"><a routerLink="/reference">Reference</a><span>/</span><span>Builtins</span></div>
      <h1 class="title">Builtins</h1>
      <p class="lead">
        What every Myla program has without an import: the built-in functions the checker knows, and the methods of the built-in types, which
        the implicit modules hold. Like the Force, they are all around you.
      </p>
      <h2 class="group">Methods of the built-in types</h2>
      <div class="grid">
        @for (m of implicit(); track m.slug) {
          <a class="card interactive mod" [routerLink]="m.route">
            <span class="name">{{ m.name }}</span>
            <span class="sum">{{ m.summary }}</span>
            <span class="count">{{ m.items }} items</span>
          </a>
        }
      </div>
      @if (section(); as html) {
        <h2 class="group">Built-in functions</h2>
        <app-doc-content [html]="html" [examples]="lib.value()?.examples ?? []" />
      }
    </app-doc-layout>
  `,
  styleUrls: ['../page.scss', './reference.scss'],
})
export class BuiltinsPage {
  private readonly content = inject(ContentService);
  readonly site = resource({ loader: () => this.content.site() });
  readonly lib = resource({ loader: () => this.content.library() });
  readonly nav = computed(() => referenceNav(this.site.value()));
  readonly implicit = computed(() => this.site.value()?.reference.filter((m) => m.implicit) ?? []);
  // the section of the library's front page between its "Built-in functions"
  // heading and the next one of that level
  readonly section = computed(() => {
    const html = this.lib.value()?.html;
    if (!html) return null;
    const start = html.indexOf('<h2 id="built-in-functions">');
    if (start < 0) return null;
    const rest = html.slice(start);
    const end = rest.indexOf('<h2', 10);
    return (end < 0 ? rest : rest.slice(0, end)).replace(/^<h2 id="built-in-functions">.*?<\/h2>/, '');
  });
}
