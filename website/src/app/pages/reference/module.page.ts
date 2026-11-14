import { ChangeDetectionStrategy, Component, computed, effect, inject, input, resource, signal } from '@angular/core';
import { Title } from '@angular/platform-browser';
import { RouterLink } from '@angular/router';
import { ContentService } from '../../core/content.service';
import { ApiItem, ModulePage, TocEntry } from '../../core/content.types';
import { DocContentComponent } from '../../content/doc-content.component';
import { DocLayoutComponent } from '../../content/doc-layout.component';
import { highlight } from '../../editor/highlight';
import { BLOB } from '../../core/links';
import { referenceNav } from './nav';

interface TypeEntry {
  item: ApiItem;
  impls: ApiItem[];
}

interface Grouped {
  types: TypeEntry[];
  functions: ApiItem[];
  constants: ApiItem[];
  foreign: { target: string; impls: ApiItem[] }[];
}

const TYPE_KINDS = new Set(['struct', 'enum', 'trait', 'type']);

// A module's API: types with the methods of their impls, functions,
// constants, and impls on other types.
export function groupItems(items: ApiItem[], filter: string): Grouped {
  const f = filter.trim().toLowerCase();
  const matches = (i: ApiItem) => !f || i.name.toLowerCase().includes(f) || i.members.some((m) => m.name.toLowerCase().includes(f));
  const types = items.filter((i) => TYPE_KINDS.has(i.kind));
  const typeNames = new Set(types.map((t) => t.name));
  const impls = items.filter((i) => i.kind === 'impl');
  const g: Grouped = { types: [], functions: [], constants: [], foreign: [] };
  for (const t of types) {
    const own = impls.filter((i) => i.target === t.name);
    if (matches(t) || own.some(matches)) g.types.push({ item: t, impls: own });
  }
  g.functions = items.filter((i) => i.kind === 'function' && matches(i));
  g.constants = items.filter((i) => i.kind === 'constant' && matches(i));
  const foreign = new Map<string, ApiItem[]>();
  for (const i of impls) {
    if (typeNames.has(i.target) || !matches(i)) continue;
    foreign.set(i.target, [...(foreign.get(i.target) ?? []), i]);
  }
  g.foreign = [...foreign].map(([target, list]) => ({ target, impls: list }));
  return g;
}

@Component({
  selector: 'app-module-page',
  imports: [DocLayoutComponent, DocContentComponent, RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './module.page.html',
  styleUrls: ['../page.scss', './reference.scss'],
})
export class ModulePageComponent {
  readonly module = input.required<string>();
  private readonly content = inject(ContentService);
  readonly blob = BLOB;
  readonly filter = signal('');
  readonly site = resource({ loader: () => this.content.site().catch(() => null) });
  readonly page = resource({ params: () => this.module(), loader: ({ params }) => this.content.module(params).catch(() => null) });
  readonly nav = computed(() => referenceNav(this.site.value()));
  readonly grouped = computed(() => (this.page.value() ? groupItems(this.page.value()!.items, this.filter()) : null));
  readonly toc = computed<TocEntry[]>(() => {
    const p = this.page.value();
    if (!p) return [];
    const toc = (p.wiki?.toc ?? []).filter((t) => t.level === 2);
    const g = this.grouped();
    const api: TocEntry[] = [{ id: 'api', text: 'API', level: 2 }];
    if (g?.types.length) api.push({ id: 'api-types', text: 'Types', level: 3 });
    if (g?.functions.length) api.push({ id: 'api-functions', text: 'Functions', level: 3 });
    if (g?.constants.length) api.push({ id: 'api-constants', text: 'Constants', level: 3 });
    if (g?.foreign.length) api.push({ id: 'api-impls', text: 'On other types', level: 3 });
    return [...toc, ...api];
  });

  constructor() {
    const title = inject(Title);
    effect(() => {
      const p = this.page.value();
      if (p) title.setTitle(`${p.name} · Myla reference`);
    });
    effect(() => {
      this.module();
      this.filter.set('');
    });
  }

  hl(code: string): string {
    return highlight(code);
  }

  src(p: ModulePage, line: number): string {
    return `${this.blob}/${p.source}#L${line}`;
  }

  implTitle(i: ApiItem): string {
    return i.trait ? `impl ${i.trait}` : 'methods';
  }

  tests(t: string[]): string {
    return t.join('\n');
  }
}
