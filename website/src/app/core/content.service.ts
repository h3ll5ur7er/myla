import { Injectable } from '@angular/core';
import { Course, DocPage, LibraryIndex, ModulePage, SearchEntry, SiteIndex } from './content.types';

// The site's content, fetched once per file from content/ (relative, so the
// site works under any base path) and kept.
@Injectable({ providedIn: 'root' })
export class ContentService {
  private cache = new Map<string, Promise<unknown>>();

  private get<T>(file: string): Promise<T> {
    let p = this.cache.get(file);
    if (!p) {
      p = fetch(`content/${file}`).then((r) => {
        if (!r.ok) throw new Error(`content/${file}: ${r.status}`);
        return r.json();
      });
      p.catch(() => this.cache.delete(file));
      this.cache.set(file, p);
    }
    return p as Promise<T>;
  }

  site(): Promise<SiteIndex> {
    return this.get('site.json');
  }

  doc(slug: string): Promise<DocPage> {
    return this.get(`docs/${slug || 'index'}.json`);
  }

  quickstart(): Promise<DocPage> {
    return this.get('quickstart.json');
  }

  module(slug: string): Promise<ModulePage> {
    return this.get(`reference/${slug}.json`);
  }

  library(): Promise<LibraryIndex> {
    return this.get('reference/index.json');
  }

  course(): Promise<Course> {
    return this.get('learn.json');
  }

  playground(): Promise<{ file: string; title: string; about: string; source: string }[]> {
    return this.get('playground.json');
  }

  search(): Promise<SearchEntry[]> {
    return this.get('search.json');
  }
}
