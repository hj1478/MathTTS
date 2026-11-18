// The problem on web: KaTeX straight into the DOM. Screen readers get `label`
// (the spoken sentence), not symbol names (Tokens.dc.html §4).
import katex from 'katex';
import { useEffect, useMemo, useRef } from 'react';

import { mathHtml, segmentCss, segmentsHtml } from '@/lib/mathHtml';
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

export function MathText({ text, label, big, segments, current, onPick }: MathTextProps) {
  const c = useColors();
  ensureKatexCss();
  const box = useRef<HTMLDivElement>(null);
  const html = useMemo(() => (segments ? segmentsHtml(segments) : mathHtml(text)), [text, segments]);
  const css = segmentCss({ bg: c.hlBg, text: c.hlText, line: c.hlLine }, !!onPick);
  // The phrase being read is marked on the nodes already there: typesetting again 4 times a second would flicker.
  useEffect(() => {
    box.current?.querySelectorAll('.seg').forEach((el, i) => el.classList.toggle('on', i === current));
  }, [html, current]);
  return (
    <div role="text" aria-label={label || undefined}>
      {segments && <style>{css}</style>}
      <div
        ref={box}
        aria-hidden={label ? true : undefined}
        onClick={
          onPick &&
          ((e) => {
            const seg = (e.target as HTMLElement).closest?.('.seg') as HTMLElement | null;
            if (seg?.dataset.i != null) onPick(Number(seg.dataset.i));
          })
        }
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
