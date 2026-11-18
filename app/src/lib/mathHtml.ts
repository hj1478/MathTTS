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

/** The problem in phrases, each a `<span class="seg" data-i>` the reading highlight can mark. */
export function segmentsHtml(segments: { md: string }[]): string {
  return segments.map((s, i) => `<span class="seg" data-i="${i}">${mathHtml(s.md)}</span>`).join('');
}

/** How a phrase looks while it is read (`.on`), and that it can be pressed. */
export const segmentCss = (hl: { bg: string; text: string; line: string }, pressable: boolean) =>
  `.seg{border-radius:4px;-webkit-box-decoration-break:clone;box-decoration-break:clone${pressable ? ';cursor:pointer' : ''}}` +
  `.seg.on,.seg.on .katex-display{background:${hl.bg};color:${hl.text};box-shadow:inset 0 -2px 0 ${hl.line}}`;
