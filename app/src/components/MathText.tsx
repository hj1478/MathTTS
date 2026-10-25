// "읽은 문제" on iOS/Android: KaTeX in a WebView that sizes itself to its content.
import { useMemo, useState } from 'react';
import { View } from 'react-native';
import katex from 'katex';
import { WebView } from 'react-native-webview';

import { plainPreview } from '@/lib/format';
import { KATEX_CSS, KATEX_CSS_VERSION } from '@/lib/katexCss.generated';
import { mathHtml } from '@/lib/mathHtml';
import { useColors } from '@/lib/theme';

export interface MathTextProps {
  text: string;
  /** What screen readers announce instead of the typeset formula. */
  label?: string;
  big?: boolean;
}

// Inlined (fonts included) so saved results typeset offline.
if (__DEV__ && KATEX_CSS_VERSION !== katex.version)
  console.warn(`katexCss.generated.ts is for katex ${KATEX_CSS_VERSION}, not ${katex.version}: run node scripts/katex-native-css.js`);

export function MathText({ text, label, big }: MathTextProps) {
  const c = useColors();
  const [height, setHeight] = useState(60);
  const html = useMemo(
    () => `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<style>${KATEX_CSS}</style>
<style>html,body{margin:0;padding:0;background:transparent;color:${c.text};
font:500 ${big ? 22 : 20}px/${big ? 42 : 38}px -apple-system,"Apple SD Gothic Neo","Noto Sans KR",sans-serif;
overflow-wrap:anywhere}</style></head><body><div id="m">${mathHtml(text)}</div>
<script>function h(){window.ReactNativeWebView.postMessage(String(document.getElementById('m').scrollHeight))}
new ResizeObserver(h).observe(document.getElementById('m'));window.onload=h;h();</script></body></html>`,
    [text, big, c.text],
  );
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
          originWhitelist={['*']}
          source={{ html }}
          scrollEnabled={false}
          style={{ backgroundColor: 'transparent' }}
          onMessage={(e) => {
            const h = Number(e.nativeEvent.data);
            if (h > 0) setHeight(Math.ceil(h) + 4);
          }}
        />
      </View>
    </View>
  );
}
