// OCR markdown with $…$ / $$…$$ → HTML, formulas typeset by KaTeX.
import katex from 'katex';

const esc = (s: string) =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

function inline(md: string): string {
  return esc(md)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/^#+\s*/gm, '')
    .replace(/\n/g, '<br>');
}

export function mathHtml(md: string): string {
  const out: string[] = [];
  const re = /\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]|\$([^$\n]+?)\$|\\\(([\s\S]+?)\\\)/g;
  let last = 0;
  for (let m; (m = re.exec(md)); ) {
    out.push(inline(md.slice(last, m.index)));
    const display = m[1] != null || m[2] != null;
    const tex = m[1] ?? m[2] ?? m[3] ?? m[4] ?? '';
    out.push(katex.renderToString(tex, { displayMode: display, throwOnError: false, output: 'html' }));
    last = re.lastIndex;
  }
  out.push(inline(md.slice(last)));
  return out.join('');
}
