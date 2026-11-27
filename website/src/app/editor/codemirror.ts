// The CodeMirror setup of <myla-editor> (MYLA-633), imported on demand so
// that pages load without it.

import { EditorState, Compartment, Extension } from '@codemirror/state';
import {
  EditorView,
  keymap,
  lineNumbers,
  highlightActiveLine,
  highlightActiveLineGutter,
  drawSelection,
  highlightSpecialChars,
  placeholder,
} from '@codemirror/view';
import { defaultKeymap, history, historyKeymap, indentWithTab } from '@codemirror/commands';
import { bracketMatching, indentOnInput, foldGutter } from '@codemirror/language';
import { closeBrackets, closeBracketsKeymap } from '@codemirror/autocomplete';
import { linter, lintGutter, Diagnostic as CmDiagnostic, forceLinting } from '@codemirror/lint';
import { highlightSelectionMatches, searchKeymap } from '@codemirror/search';
import { myla } from './myla-language';
import type { Diagnostic } from '../core/toolchain.service';

export interface EditorHooks {
  onChange(code: string): void;
  onRun(): void;
  check(code: string): Promise<Diagnostic[] | null>;
}

const theme = EditorView.theme({
  '&': {
    color: 'var(--code-text)',
    backgroundColor: 'transparent',
    fontSize: '14px',
  },
  '.cm-content': { fontFamily: 'var(--font-mono)', padding: '14px 0', caretColor: 'var(--cyan)' },
  '.cm-scroller': { fontFamily: 'var(--font-mono)', lineHeight: '1.6' },
  '&.cm-focused': { outline: 'none' },
  '.cm-gutters': { backgroundColor: 'transparent', color: 'var(--text-faint)', border: 'none', paddingLeft: '6px' },
  '.cm-activeLine': { backgroundColor: 'rgba(139, 92, 246, 0.07)' },
  '.cm-activeLineGutter': { backgroundColor: 'transparent', color: 'var(--text-muted)' },
  '.cm-selectionBackground, &.cm-focused .cm-selectionBackground, ::selection': { backgroundColor: 'rgba(139, 92, 246, 0.3) !important' },
  '.cm-cursor': { borderLeftColor: 'var(--cyan)', borderLeftWidth: '2px' },
  '.cm-matchingBracket': { backgroundColor: 'rgba(34, 211, 238, 0.18)', outline: '1px solid rgba(34, 211, 238, 0.4)' },
  '.cm-tooltip': { backgroundColor: 'var(--bg-raised)', border: '1px solid var(--border-strong)', borderRadius: '8px', color: 'var(--text)' },
  '.cm-tooltip-lint': { fontFamily: 'var(--font-body)', fontSize: '13px' },
  '.cm-diagnostic': { padding: '6px 10px' },
  '.cm-diagnostic-error': { borderLeft: '3px solid var(--red)' },
  '.cm-diagnostic-warning': { borderLeft: '3px solid var(--amber)' },
  '.cm-lintRange-error': { backgroundImage: 'none', textDecoration: 'underline wavy var(--red)', textUnderlineOffset: '3px' },
  '.cm-lintRange-warning': { backgroundImage: 'none', textDecoration: 'underline wavy var(--amber)', textUnderlineOffset: '3px' },
  '.cm-placeholder': { color: 'var(--text-faint)' },
  '.cm-foldGutter span': { color: 'var(--text-faint)' },
});

// A position of the document from a 1-based line and column, clamped.
function pos(state: EditorState, line: number, col: number): number {
  const l = state.doc.line(Math.min(Math.max(1, line), state.doc.lines));
  return Math.min(l.to, l.from + Math.max(0, col - 1));
}

export function toCm(state: EditorState, ds: Diagnostic[]): CmDiagnostic[] {
  return ds
    .filter((d) => d.line > 0)
    .map((d) => {
      const from = pos(state, d.line, d.col);
      let to = d.endLine ? pos(state, d.endLine, d.endCol) : from;
      if (to <= from) to = Math.min(state.doc.length, from + 1);
      const notes = d.notes?.length ? '\n' + d.notes.map((n) => `${n.label}: ${n.message}`).join('\n') : '';
      return { from, to, severity: d.severity === 'warning' ? 'warning' : 'error', source: d.kind, message: d.message + notes } as CmDiagnostic;
    });
}

export interface MylaView {
  view: EditorView;
  setCode(code: string): void;
  setEditable(on: boolean): void;
  relint(): void;
  destroy(): void;
}

export function createView(parent: HTMLElement, code: string, hooks: EditorHooks, opts: { editable: boolean; lint: boolean; placeholder?: string }): MylaView {
  const editable = new Compartment();
  const extensions: Extension[] = [
    lineNumbers(),
    highlightActiveLineGutter(),
    highlightSpecialChars(),
    foldGutter(),
    history(),
    drawSelection(),
    indentOnInput(),
    bracketMatching(),
    closeBrackets(),
    highlightActiveLine(),
    highlightSelectionMatches(),
    EditorState.tabSize.of(4),
    keymap.of([
      { key: 'Mod-Enter', run: () => (hooks.onRun(), true) },
      { key: 'Shift-Enter', run: () => (hooks.onRun(), true) },
      ...closeBracketsKeymap,
      ...defaultKeymap,
      ...historyKeymap,
      ...searchKeymap,
      indentWithTab,
    ]),
    myla(),
    theme,
    editable.of([EditorView.editable.of(opts.editable), EditorState.readOnly.of(!opts.editable)]),
    EditorView.updateListener.of((u) => {
      if (u.docChanged) hooks.onChange(u.state.doc.toString());
    }),
  ];
  if (opts.placeholder) extensions.push(placeholder(opts.placeholder));
  if (opts.lint) {
    extensions.push(
      lintGutter(),
      linter(
        async (view) => {
          const ds = await hooks.check(view.state.doc.toString());
          return ds ? toCm(view.state, ds) : [];
        },
        { delay: 600 },
      ),
    );
  }
  const view = new EditorView({ state: EditorState.create({ doc: code, extensions }), parent });
  return {
    view,
    setCode(c: string) {
      view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: c } });
    },
    setEditable(on: boolean) {
      view.dispatch({ effects: editable.reconfigure([EditorView.editable.of(on), EditorState.readOnly.of(!on)]) });
    },
    relint() {
      forceLinting(view);
    },
    destroy() {
      view.destroy();
    },
  };
}
