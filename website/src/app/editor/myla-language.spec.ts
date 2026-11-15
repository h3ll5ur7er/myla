import { describe, expect, it } from 'vitest';
import { StringStream } from '@codemirror/language';
import { MylaState, token } from './myla-language';

// The tokens of each line of `src`, as [text, style] pairs (spaces dropped).
function tokens(src: string): [string, string | null][] {
  const state: MylaState = { stack: [], comment: false };
  const out: [string, string | null][] = [];
  for (const line of src.split('\n')) {
    const s = new StringStream(line, 4, 4);
    while (!s.eol()) {
      const style = token(s, state);
      const text = s.current();
      if (text.trim()) out.push([text, style]);
      s.start = s.pos;
    }
  }
  return out;
}

describe('the Myla mode', () => {
  it('tells keywords, types, functions, builtins, constants and variables apart', () => {
    expect(tokens('pub fun area(s: Shape) -> int { return print(Some(x)) }')).toEqual([
      ['pub', 'keyword'], ['fun', 'keyword'], ['area', 'function'], ['(', 'punctuation'], ['s', 'variableName'], [':', 'punctuation'],
      ['Shape', 'typeName'], [')', 'punctuation'], ['->', 'operator'], ['int', 'typeName'], ['{', 'punctuation'], ['return', 'keyword'],
      ['print', 'standard'], ['(', 'punctuation'], ['Some', 'atom'], ['(', 'punctuation'], ['x', 'variableName'], [')', 'punctuation'],
      [')', 'punctuation'], ['}', 'punctuation'],
    ]);
  });

  it('reads numbers with suffixes, bases and fractions, chars and attributes', () => {
    const got = tokens("#test(255u8, 0xFF_FF, 1.5e-3, 2f32, 'a', '\\u{1F600}')");
    expect(got.filter(([, s]) => s !== 'punctuation')).toEqual([
      ['#test', 'meta'], ['255u8', 'number'], ['0xFF_FF', 'number'], ['1.5e-3', 'number'], ['2f32', 'number'], ["'a'", 'string.special'], ["'\\u{1F600}'", 'string.special'],
    ]);
  });

  it("keeps a range's dots and a tuple index apart from a fraction", () => {
    expect(tokens('0..10').map(([s]) => s)).toEqual(['0', '..', '10']);
  });

  it('highlights the expressions of an f-string, strings inside them too', () => {
    const got = tokens('f"{name} has {n * 2} {"braces"}: {{}}"');
    expect(got).toContainEqual(['name', 'variableName']);
    expect(got).toContainEqual(['n', 'variableName']);
    expect(got).toContainEqual(['2', 'number']);
    expect(got).toContainEqual(['"braces"', 'string']);
    expect(got.at(-1)).toEqual(['"', 'string']);
  });

  it('carries a block comment over lines, but not nested', () => {
    expect(tokens('a /* one\ntwo */ b')).toEqual([['a', 'variableName'], ['/* one', 'comment'], ['two */', 'comment'], ['b', 'variableName']]);
  });

  it('ends line comments and strings with escapes', () => {
    expect(tokens('"a\\"b" // done')).toEqual([['"a\\"b"', 'string'], ['// done', 'comment']]);
  });
});
