import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', loadComponent: () => import('./pages/home/home.page').then((m) => m.HomePage), title: "Myla — a language that compiles itself. Don't panic." },
  { path: 'quickstart', loadComponent: () => import('./pages/quickstart/quickstart.page').then((m) => m.QuickstartPage), title: 'Quickstart · Myla' },
  { path: 'download', loadComponent: () => import('./pages/download/download.page').then((m) => m.DownloadPage), title: 'Download · Myla' },
  { path: 'docs', loadComponent: () => import('./pages/docs/docs.page').then((m) => m.DocsPage) },
  { path: 'docs/:slug', loadComponent: () => import('./pages/docs/docs.page').then((m) => m.DocsPage) },
  { path: 'reference', loadComponent: () => import('./pages/reference/reference-index.page').then((m) => m.ReferenceIndexPage), title: 'Reference · Myla' },
  { path: 'reference/builtins', loadComponent: () => import('./pages/reference/builtins.page').then((m) => m.BuiltinsPage), title: 'Builtins · Myla' },
  { path: 'reference/:module', loadComponent: () => import('./pages/reference/module.page').then((m) => m.ModulePageComponent) },
  { path: 'learn', loadComponent: () => import('./pages/learn/learn-map.page').then((m) => m.LearnMapPage), title: 'Learn · Myla' },
  { path: 'learn/profile', loadComponent: () => import('./pages/learn/profile.page').then((m) => m.ProfilePage), title: 'Your journey · Myla' },
  { path: 'learn/:chapter', loadComponent: () => import('./pages/learn/chapter.page').then((m) => m.ChapterPage) },
  { path: 'learn/:chapter/:exercise', loadComponent: () => import('./pages/learn/exercise.page').then((m) => m.ExercisePage) },
  { path: 'playground', loadComponent: () => import('./pages/playground/playground.page').then((m) => m.PlaygroundPage), title: 'Playground · Myla' },
  { path: '**', loadComponent: () => import('./pages/not-found/not-found.page').then((m) => m.NotFoundPage), title: '404 · Myla' },
];
