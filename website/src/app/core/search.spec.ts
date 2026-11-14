import { describe, expect, it } from 'vitest';
import { score, search } from './search';

const e = (t: string, k = 'Function', d = '') => ({ t, u: '/', k, d });

describe('search', () => {
  it('ranks exact, prefix, word start, inside and in-order matches', () => {
    const q = 'split';
    expect(score(e('split'), q)).toBeGreaterThan(score(e('splitn'), q));
    expect(score(e('splitn'), q)).toBeGreaterThan(score(e('str.split_whitespace'), q));
    expect(score(e('str.split_whitespace'), q)).toBeGreaterThan(score(e('resplit'), q));
    expect(score(e('resplit'), q)).toBeGreaterThan(score(e('sp_l_i_t'), q));
    expect(score(e('nothing'), q)).toBe(0);
  });

  it('finds by the detail line last, and modules before members', () => {
    expect(score(e('read', 'Function', 'std.fs · fun read_to_string()'), 'read_to')).toBeGreaterThan(0);
    expect(score(e('std.json', 'Module'), 'std.json')).toBeGreaterThan(score(e('std.json', 'Function'), 'std.json'));
  });

  it('returns the best first, at most the limit', () => {
    const got = search([e('mapper'), e('map'), e('heap')], 'map', 2);
    expect(got.map((x) => x.t)).toEqual(['map', 'mapper']);
    expect(search([e('a')], '   ')).toEqual([]);
  });
});
