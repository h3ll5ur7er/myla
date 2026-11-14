import { ChangeDetectionStrategy, Component, computed, effect, inject, input, resource } from '@angular/core';
import { Title } from '@angular/platform-browser';
import { RouterLink } from '@angular/router';
import { ContentService } from '../../core/content.service';
import { DocContentComponent } from '../../content/doc-content.component';
import { DocLayoutComponent, NavGroup } from '../../content/doc-layout.component';
import { BLOB } from '../../core/links';

// A page of the language docs: the wiki's docs/Language pages (MYLA-631).
@Component({
  selector: 'app-docs-page',
  imports: [DocLayoutComponent, DocContentComponent, RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <app-doc-layout [nav]="nav()" [toc]="page.value()?.toc ?? []" [ready]="!!page.value()">
      @if (page.value(); as p) {
        <div class="crumbs"><a routerLink="/docs">Docs</a>@if (p.slug) {<span>/</span><span>{{ p.title }}</span>}</div>
        <h1 class="title">{{ p.slug ? p.title : 'The Myla language' }}</h1>
        <app-doc-content [html]="p.html" [examples]="p.examples" />
        <div class="pager">
          @if (p.prev; as prev) {
            <a class="card interactive prev" [routerLink]="prev.route"><span>← Previous</span><b>{{ prev.title }}</b></a>
          } @else {
            <span></span>
          }
          @if (p.next; as next) {
            <a class="card interactive next" [routerLink]="next.route"><span>Next →</span><b>{{ next.title }}</b></a>
          }
        </div>
        <p class="edit"><a [href]="blob + '/' + p.source" target="_blank" rel="noopener">Edit this page on GitHub</a> · the site's docs are the repository's wiki.</p>
      } @else if (page.value() === null) {
        <h1>Lost in hyperspace</h1>
        <p>This page couldn't be loaded. <a routerLink="/docs">Back to the docs</a>.</p>
      } @else {
        <div class="skeleton"><i></i><i></i><i></i><i></i></div>
      }
    </app-doc-layout>
  `,
  styleUrl: '../page.scss',
})
export class DocsPage {
  readonly slug = input<string>('');
  private readonly content = inject(ContentService);
  readonly blob = BLOB;
  readonly site = resource({ loader: () => this.content.site().catch(() => null) });
  readonly page = resource({ params: () => this.slug() ?? '', loader: ({ params }) => this.content.doc(params).catch(() => null) });
  readonly nav = computed<NavGroup[]>(() => {
    const s = this.site.value();
    if (!s) return [];
    return [
      { title: 'The language', links: s.docs.map((d) => ({ label: d.slug ? d.title : 'Overview', route: d.route })) },
      { title: 'More', links: [{ label: 'Standard library', route: '/reference' }, { label: 'Builtins', route: '/reference/builtins' }, { label: 'Quickstart', route: '/quickstart' }] },
    ];
  });

  constructor() {
    const title = inject(Title);
    effect(() => {
      const p = this.page.value();
      if (p) title.setTitle(`${p.slug ? p.title : 'Docs'} · Myla`);
    });
  }
}
