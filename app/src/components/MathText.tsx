// The problem on iOS/Android: KaTeX in a WebView that sizes itself to its content.
import { useEffect, useMemo, useRef, useState } from 'react';
import { View } from 'react-native';
import katex from 'katex';
import { WebView } from 'react-native-webview';

import { plainPreview } from '@/lib/format';
import { KATEX_CSS, KATEX_CSS_VERSION } from '@/lib/katexCss.generated';
import { mathHtml, segmentCss, segmentsHtml } from '@/lib/mathHtml';
import { useColors } from '@/lib/theme';

export interface MathTextProps {
  text: string;
  /** What screen readers announce instead of the typeset formula. */
  label?: string;
  big?: boolean;
  /** The same text in phrases (lib/format readingSegments), for the reading highlight. */
  segments?: { md: string }[];
  /** The phrase being read, -1 for none. */
  current?: number;
  /** A phrase was pressed. */
  onPick?: (i: number) => void;
}

// Inlined (fonts included) so saved results typeset offline.
if (__DEV__ && KATEX_CSS_VERSION !== katex.version)
  console.warn(`katexCss.generated.ts is for katex ${KATEX_CSS_VERSION}, not ${katex.version}: run node scripts/katex-native-css.js`);

const mark = (i: number) =>
  `document.querySelectorAll('.seg').forEach(function(e,k){e.classList.toggle('on',k===${i})});true;`;

export function MathText({ text, label, big, segments, current = -1, onPick }: MathTextProps) {
  const c = useColors();
  const [height, setHeight] = useState(60);
  const web = useRef<WebView<object>>(null);
  const pressable = !!onPick;
  const html = useMemo(
    () => `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<style>${KATEX_CSS}</style>
<style>html,body{margin:0;padding:0;background:transparent;color:${c.text};
font:500 ${big ? 22 : 20}px/${big ? 42 : 38}px -apple-system,"Apple SD Gothic Neo","Noto Sans KR",sans-serif;
overflow-wrap:anywhere;-webkit-tap-highlight-color:transparent}
${segments ? segmentCss({ bg: c.hlBg, text: c.hlText, line: c.hlLine }, pressable) : ''}</style></head>
<body><div id="m">${segments ? segmentsHtml(segments) : mathHtml(text)}</div>
<script>var RN=window.ReactNativeWebView;
function h(){RN.postMessage(String(document.getElementById('m').scrollHeight))}
new ResizeObserver(h).observe(document.getElementById('m'));window.onload=h;h();
document.addEventListener('click',function(e){var s=e.target.closest&&e.target.closest('.seg');if(s)RN.postMessage('seg:'+s.dataset.i)});
</script></body></html>`,
    [text, segments, big, pressable, c.text, c.hlBg, c.hlText, c.hlLine],
  );
  // The phrase being read is marked inside the page: a new page 4 times a second would flicker.
  useEffect(() => {
    web.current?.injectJavaScript(mark(current));
  }, [current, html]);
  return (
    <View
      accessible
      // Until the spoken sentence exists (mid-processing), the plain text.
      accessibilityLabel={label || plainPreview(text)}
      importantForAccessibility="yes"
      style={{ height }}
    >
      <View style={{ flex: 1 }} importantForAccessibility="no-hide-descendants" accessibilityElementsHidden>
        <WebView
          ref={web}
          originWhitelist={['*']}
          source={{ html }}
          scrollEnabled={false}
          style={{ backgroundColor: 'transparent' }}
          onLoadEnd={() => {
            web.current?.injectJavaScript(mark(current));
          }}
          onMessage={(e) => {
            const d = e.nativeEvent.data;
            if (d.startsWith('seg:')) return onPick?.(Number(d.slice(4)));
            const h = Number(d);
            if (h > 0) setHeight(Math.ceil(h) + 4);
          }}
        />
      </View>
    </View>
  );
}
