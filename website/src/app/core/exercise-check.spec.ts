import { describe, expect, it } from 'vitest';
import { checkedProgram, testsOf } from './exercise-check';

const starter = `// title: T
#test(4)[10]
#test(0)[0]
fun triangle(n: int) -> int {
    return 0
}

fun helper() -> int { return 1 }
`;

describe('testsOf', () => {
  it("finds each tested function's cases", () => {
    expect(testsOf(starter)).toEqual([{ fn: 'triangle', lines: ['#test(4)[10]', '#test(0)[0]'] }]);
  });

  it('reads a case that spans lines, and methods and generic functions', () => {
    const src = '#test(f("ab" +\n    "cd"))[1]\npub fun g<T>(x: T) -> int {\n}\nimpl P {\n    #test()[2]\n    fun m(self) -> int { return 2 }\n}\n';
    expect(testsOf(src)).toEqual([
      { fn: 'g', lines: ['#test(f("ab" +\n    "cd"))[1]'] },
      { fn: 'm', lines: ['#test()[2]'] },
    ]);
  });
});

describe('checkedProgram', () => {
  const own = testsOf(starter);

  it("replaces the learner's cases with the exercise's own", () => {
    const learner = '#test(1)[1]\nfun triangle(n: int) -> int {\n    return 1\n}\n';
    const r = checkedProgram(learner, own, [], 0);
    expect(r).toEqual({ source: '#test(4)[10]\n#test(0)[0]\nfun triangle(n: int) -> int {\n    return 1\n}\n', cases: 2 });
  });

  it('adds the hidden cases, and indents them like the function', () => {
    const learner = 'impl P {\n    fun m(self) -> int { return 2 }\n}\n';
    const r = checkedProgram(learner, [], [{ fn: 'm', lines: ['#test()[2]'] }], 0);
    expect(r).toEqual({ source: 'impl P {\n    #test()[2]\n    fun m(self) -> int { return 2 }\n}\n', cases: 1 });
  });

  it('removes a case that spans lines', () => {
    const learner = '#test(f("a" +\n  "b"))[1]\nfun triangle(n: int) -> int { return 0 }\n';
    const r = checkedProgram(learner, own, [], 0);
    expect('source' in r && r.source.startsWith('#test(4)[10]\n#test(0)[0]\nfun triangle')).toBe(true);
  });

  it('names a tested function the learner removed or renamed', () => {
    expect(checkedProgram('fun triangl(n: int) -> int { return 0 }\n', own, [], 0)).toEqual({ missing: 'triangle' });
  });

  it("keeps the learner's own cases when the exercise asks for them", () => {
    const learner = '#test(6, 7)[42]\n#test(1, 1)[1]\nfun question(a: int, b: int) -> int { return a * b }\n';
    const r = checkedProgram(learner, [], [{ fn: 'question', lines: ['#test(3, 5)[15]'] }], 2);
    expect(r).toEqual({ source: '#test(6, 7)[42]\n#test(1, 1)[1]\n#test(3, 5)[15]\nfun question(a: int, b: int) -> int { return a * b }\n', cases: 3 });
  });

  it("doesn't take a #test inside a string or a comment for a case", () => {
    const learner = 'fun triangle(n: int) -> int {\n    // #test(1)[1] is how a case looks\n    return 0\n}\n';
    const r = checkedProgram(learner, own, [], 0);
    expect('source' in r && r.source.includes('// #test(1)[1] is how')).toBe(true);
  });
});
