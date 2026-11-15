import { StringStream } from '@codemirror/language';
import { MylaState, token } from './myla-language';

const ESC: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' };
const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ESC[c]);

// Myla code as HTML with a span per token, classed `tok-<style>`, for code
// shown without an editor (the reference's signatures and examples).
export function highlight(code: string): string {
  const state: MylaState = { stack: [], comment: false };
  const out: string[] = [];
  const lines = code.split('\n');
  lines.forEach((line, i) => {
    const s = new StringStream(line, 4, 4);
    while (!s.eol()) {
      const style = token(s, state);
      const text = s.current();
      out.push(style ? `<span class="tok-${style.replace('.', '-')}">${esc(text)}</span>` : esc(text));
      s.start = s.pos;
    }
    if (i < lines.length - 1) out.push('\n');
  });
  return out.join('');
}
