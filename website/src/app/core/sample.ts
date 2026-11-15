// A sample program's source and its expected output, from its trailing
// `// output:` comment (`//` alone an empty line), as the wiki's blocks
// write it (scripts/lib/markdown.mjs's parseExample).
export function splitOutput(text: string): { source: string; output: string | null } {
  const lines = text.replace(/\s+$/, '').split('\n');
  const at = lines.findIndex((l) => /^\/\/ output:\s*$/.test(l));
  if (at < 0 || !lines.slice(at + 1).every((l) => /^\/\/( |$)/.test(l))) return { source: lines.join('\n') + '\n', output: null };
  const output = lines.slice(at + 1).map((l) => (l === '//' ? '' : l.slice(3))).join('\n') + '\n';
  return { source: lines.slice(0, at).join('\n').replace(/\s+$/, '') + '\n', output };
}
