// "읽은 문제" on web: KaTeX straight into the DOM. Screen readers get `label`
// (the spoken sentence), not symbol names (Tokens.dc.html §4).
import katex from 'katex';
import { useMemo } from 'react';

import { mathHtml } from '@/lib/mathHtml';
import { useColors } from '@/lib/theme';
import type { MathTextProps } from './MathText';

// Metro bundles the CSS but not the fonts it points at, so load both from the CDN.
function ensureKatexCss() {
  if (document.getElementById('katex-css')) return;
  const link = document.createElement('link');
  link.id = 'katex-css';
  link.rel = 'stylesheet';
  link.href = `https://cdn.jsdelivr.net/npm/katex@${katex.version}/dist/katex.min.css`;
  document.head.appendChild(link);
}

export function MathText({ text, label, big }: MathTextProps) {
  const c = useColors();
  ensureKatexCss();
  const html = useMemo(() => mathHtml(text), [text]);
  return (
    <div role="text" aria-label={label || undefined}>
      <div
        aria-hidden={label ? true : undefined}
        style={{
          fontFamily: '"IBM Plex Sans KR", IBMPlexSansKR_500Medium, system-ui, sans-serif',
          fontWeight: 500,
          fontSize: big ? 22 : 20,
          lineHeight: big ? '42px' : '38px',
          color: c.text,
          overflowWrap: 'anywhere',
        }}
        dangerouslySetInnerHTML={{ __html: html }}
      />
    </div>
  );
}
