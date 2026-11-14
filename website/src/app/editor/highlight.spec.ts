import { describe, expect, it } from 'vitest';
import { highlight } from './highlight';

describe('highlight', () => {
  it('wraps tokens and escapes HTML', () => {
    expect(highlight('fun f() -> [int] { return a < b }')).toBe(
      '<span class="tok-keyword">fun</span> <span class="tok-function">f</span><span class="tok-punctuation">(</span><span class="tok-punctuation">)</span> ' +
        '<span class="tok-operator">-&gt;</span> <span class="tok-punctuation">[</span><span class="tok-typeName">int</span><span class="tok-punctuation">]</span> ' +
        '<span class="tok-punctuation">{</span> <span class="tok-keyword">return</span> <span class="tok-variableName">a</span> <span class="tok-operator">&lt;</span> ' +
        '<span class="tok-variableName">b</span> <span class="tok-punctuation">}</span>',
    );
  });

  it('keeps lines', () => {
    expect(highlight('a\nb').split('\n').length).toBe(2);
  });
});
