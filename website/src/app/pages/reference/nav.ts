import { SiteIndex } from '../../core/content.types';
import { NavGroup } from '../../content/doc-layout.component';

// The reference's sidebar: the front page and the builtins, then the
// modules by group (scripts/content.mjs's GROUPS).
export function referenceNav(s: SiteIndex | undefined): NavGroup[] {
  if (!s) return [];
  const byName = new Map(s.reference.map((m) => [m.slug, m]));
  return [
    { title: 'Reference', links: [{ label: 'Overview', route: '/reference' }, { label: 'Builtins', route: '/reference/builtins' }] },
    ...s.groups.map((g) => ({
      title: g.title,
      links: g.modules.map((n) => ({ label: `std.${n}`, route: `/reference/${n}`, badge: String(byName.get(n)?.items ?? '') })),
    })),
  ];
}
