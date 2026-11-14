// The shapes of the JSON scripts/content.mjs writes (MYLA-631, D208).

export type ExampleKind = 'run' | 'check' | 'fragment' | 'error';

export interface Example {
  source: string;
  output: string | null;
  kind: ExampleKind;
}

export interface TocEntry {
  id: string;
  text: string;
  level: number;
}

export interface PageLink {
  title: string;
  route: string;
}

export interface DocPage {
  slug: string;
  title: string;
  html: string;
  examples: Example[];
  toc: TocEntry[];
  source: string;
  prev: PageLink | null;
  next: PageLink | null;
}

export interface ApiMember {
  name: string;
  kind: string;
  signature: string;
  doc: string;
  tests: string[];
  line: number;
}

export interface ApiItem extends ApiMember {
  id: string;
  target: string;
  trait: string;
  members: ApiMember[];
}

export interface ModulePage {
  name: string;
  slug: string;
  implicit: boolean;
  summary: string;
  moduleDoc: string;
  wiki: { title: string; html: string; examples: Example[]; toc: TocEntry[]; source: string } | null;
  items: ApiItem[];
  source: string;
}

export interface LibraryIndex {
  title: string;
  html: string;
  examples: Example[];
  toc: TocEntry[];
  source: string;
}

export interface SiteIndex {
  docs: { slug: string; title: string; route: string; sections: number }[];
  reference: { name: string; slug: string; route: string; summary: string; items: number; implicit: boolean }[];
  groups: { title: string; modules: string[] }[];
  chapters: { id: string; title: string; emoji: string; exercises: number }[];
}

export interface SearchEntry {
  t: string; // title
  u: string; // route, perhaps with #anchor
  k: string; // kind: Docs, Module, Function, Method, Learn, …
  d: string; // detail line
}

export interface Exercise {
  id: string;
  file: string;
  title: string;
  xp: number;
  boss: boolean;
  mode: 'test' | 'output';
  expected: string | null;
  hints: string[];
  instructions: string;
  starter: string;
  solution: string;
}

export interface Chapter {
  id: string;
  title: string;
  emoji: string;
  tagline: string;
  intro: string;
  exercises: Exercise[];
}

export interface Course {
  chapters: Chapter[];
  totalXp: number;
}
