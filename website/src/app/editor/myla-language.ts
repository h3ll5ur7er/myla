import { HighlightStyle, LanguageSupport, StreamLanguage, StringStream, syntaxHighlighting } from '@codemirror/language';
import { tags as t } from '@lezer/highlight';

// Myla's syntax for CodeMirror (MYLA-633, D208): the tokens of
// docs/Language/Lexical-structure.md. f-strings embed expressions in `{ }`
// (with `{{` and `}}` literal braces), which may hold strings of their own,
// so the state keeps a stack of what is open.

export const KEYWORDS = new Set([
  'let', 'var', 'fun', 'return', 'become', 'actor', 'async', 'await', 'struct', 'enum', 'impl', 'trait', 'self',
  'match', 'typealias', 'as', 'pub', 'import', 'from', 'const', 'break', 'continue', 'if', 'else', 'while', 'for', 'in',
  // contextual
  'defer',
]);
export const TYPES = new Set([
  'bool', 'str', 'char', 'int', 'float', 'int8', 'int16', 'int32', 'int64', 'uint8', 'uint16', 'uint32', 'uint64',
  'float32', 'float64', 'Self', 'Option', 'Result', 'StringBuilder',
]);
export const CONSTANTS = new Set(['true', 'false', 'None', 'Some', 'Ok', 'Err']);
export const BUILTINS = new Set(['print', 'format', 'assert', 'panic', 'unreachable']);

// What is open: an f-string (`fstr`), or an expression inside one (`expr`,
// with its brace depth).
type Frame = { kind: 'fstr' } | { kind: 'expr'; depth: number };

export interface MylaState {
  stack: Frame[];
  comment: boolean; // inside /* */
}

function top(s: MylaState): Frame | undefined {
  return s.stack[s.stack.length - 1];
}

function escape(stream: StringStream): void {
  // after the backslash: \u{…} or one character
  if (stream.eat('u') && stream.eat('{')) stream.eatWhile(/[0-9a-fA-F]/), stream.eat('}');
  else stream.next();
}

function plainString(stream: StringStream, quote: string): string {
  while (!stream.eol()) {
    const c = stream.next();
    if (c === '\\') escape(stream);
    else if (c === quote) break;
  }
  return 'string';
}

// Inside an f-string: its text up to a hole, the closing quote, or the end.
function fstrText(stream: StringStream, state: MylaState): string {
  if (stream.match('{{') || stream.match('}}')) return 'string';
  if (stream.eat('{')) {
    state.stack.push({ kind: 'expr', depth: 0 });
    return 'punctuation';
  }
  if (stream.eat('"')) {
    state.stack.pop();
    return 'string';
  }
  while (!stream.eol()) {
    const c = stream.peek();
    if (c === '"' || c === '{' || c === '}') break;
    stream.next();
    if (c === '\\') escape(stream);
  }
  return 'string';
}

export function token(stream: StringStream, state: MylaState): string | null {
  if (state.comment) {
    if (stream.skipTo('*/')) {
      stream.match('*/');
      state.comment = false;
    } else stream.skipToEnd();
    return 'comment';
  }
  const f = top(state);
  if (f?.kind === 'fstr') return fstrText(stream, state);
  if (stream.eatSpace()) return null;
  if (stream.match('//')) {
    stream.skipToEnd();
    return 'comment';
  }
  if (stream.match('/*')) {
    state.comment = true;
    return token(stream, state) ?? 'comment';
  }
  if (f?.kind === 'expr') {
    if (stream.peek() === '{') {
      f.depth++;
      stream.next();
      return 'punctuation';
    }
    if (stream.peek() === '}') {
      stream.next();
      if (f.depth === 0) {
        state.stack.pop();
        return 'punctuation';
      }
      f.depth--;
      return 'punctuation';
    }
  }
  if (stream.match('f"')) {
    state.stack.push({ kind: 'fstr' });
    return 'string';
  }
  if (stream.eat('"')) return plainString(stream, '"');
  if (stream.match(/^'(\\(u\{[0-9a-fA-F]+\}|.)|[^\\'])'/u)) return 'string.special';
  if (stream.match(/^#!?[a-z_]+/)) return 'meta';
  // numbers: hex, octal, binary, decimal with a fraction or an exponent, a suffix
  if (stream.match(/^0x[0-9a-fA-F_]+([iu](8|16|32|64))?/) || stream.match(/^0o[0-7_]+([iu](8|16|32|64))?/) || stream.match(/^0b[01_]+([iu](8|16|32|64))?/)) {
    return 'number';
  }
  if (stream.match(/^\d[\d_]*(\.\d[\d_]*)?([eE][+-]?\d+)?([iu](8|16|32|64)|f(32|64))?/)) return 'number';
  if (stream.match(/^[A-Za-z_][A-Za-z0-9_]*/)) {
    const w = stream.current();
    if (KEYWORDS.has(w)) return w === 'self' ? 'self' : 'keyword';
    if (CONSTANTS.has(w)) return 'atom';
    if (TYPES.has(w) || /^[A-Z]/.test(w)) return 'typeName';
    if (stream.match(/^\s*(<[^>]*>)?\s*\(/, false)) return BUILTINS.has(w) ? 'standard' : 'function';
    return 'variableName';
  }
  if (stream.match(/^(=>|->|\|>|>>|==|!=|<=|>=|&&|\|\||\+=|-=|\*=|\/=|%=|\.\.=?|::|\?)/)) return 'operator';
  const c = stream.next();
  if (c && '+-*/%=<>!&|^~'.includes(c)) return 'operator';
  return 'punctuation';
}

export const mylaStream = StreamLanguage.define<MylaState>({
  name: 'myla',
  startState: () => ({ stack: [], comment: false }),
  copyState: (s) => ({ stack: s.stack.map((f) => ({ ...f })), comment: s.comment }),
  token,
  languageData: { commentTokens: { line: '//', block: { open: '/*', close: '*/' } }, closeBrackets: { brackets: ['(', '[', '{', '"', "'"] } },
  tokenTable: {
    keyword: t.keyword,
    self: t.self,
    atom: t.bool,
    typeName: t.typeName,
    function: t.function(t.variableName),
    standard: t.standard(t.function(t.variableName)),
    variableName: t.variableName,
    string: t.string,
    'string.special': t.character,
    number: t.number,
    comment: t.comment,
    meta: t.meta,
    operator: t.operator,
    punctuation: t.punctuation,
  },
});

export const mylaHighlight = HighlightStyle.define([
  { tag: [t.keyword, t.self], color: 'var(--tok-keyword)', fontWeight: '500' },
  { tag: t.typeName, color: 'var(--tok-type)' },
  { tag: [t.function(t.variableName), t.standard(t.function(t.variableName))], color: 'var(--tok-function)' },
  { tag: [t.string, t.character], color: 'var(--tok-string)' },
  { tag: t.number, color: 'var(--tok-number)' },
  { tag: t.bool, color: 'var(--tok-constant)' },
  { tag: t.comment, color: 'var(--tok-comment)', fontStyle: 'italic' },
  { tag: t.meta, color: 'var(--tok-attribute)' },
  { tag: t.operator, color: 'var(--tok-operator)' },
  { tag: t.punctuation, color: 'var(--text-muted)' },
]);

export function myla(): LanguageSupport {
  return new LanguageSupport(mylaStream, [syntaxHighlighting(mylaHighlight)]);
}
