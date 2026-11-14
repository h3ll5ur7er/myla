import { describe, expect, it } from 'vitest';
import { splitOutput } from './sample';

describe('splitOutput', () => {
  it('takes the output trailer off', () => {
    expect(splitOutput('fun main() {}\n// output:\n// a\n//\n// b\n')).toEqual({ source: 'fun main() {}\n', output: 'a\n\nb\n' });
  });

  it('leaves a program without one alone', () => {
    expect(splitOutput('// output: is not the end\nfun main() {}\n')).toEqual({ source: '// output: is not the end\nfun main() {}\n', output: null });
  });
});
