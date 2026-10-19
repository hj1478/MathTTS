// 2 문제 영역 자르기 (Crop.dc.html): drag four corners, rotate, or use the whole photo.
import { router } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Image, PanResponder, View } from 'react-native';

import { Banner, Button, Header, Page, T } from '@/components/ui';
import { warmup } from '@/lib/api';
import { prepareUpload, rotate90, type Rect } from '@/lib/image';
import { session, type Picked } from '@/lib/store';
import { font, useColors } from '@/lib/theme';

const MIN = 48; // smallest crop box side, in screen px
type Corner = 'tl' | 'tr' | 'bl' | 'br';
const CORNER_LABEL: Record<Corner, string> = {
  tl: '왼쪽 위 모서리 조절',
  tr: '오른쪽 위 모서리 조절',
  bl: '왼쪽 아래 모서리 조절',
  br: '오른쪽 아래 모서리 조절',
};

function Handle({
  corner,
  rect,
  bounds,
  onChange,
}: {
  corner: Corner;
  rect: Rect;
  bounds: { w: number; h: number };
  onChange: (r: Rect) => void;
}) {
  const c = useColors();
  const live = useRef({ rect, bounds, onChange, start: rect });
  useEffect(() => {
    Object.assign(live.current, { rect, bounds, onChange });
  });

  // The handlers read `live` when a gesture happens, never during render.
  // eslint-disable-next-line react-hooks/refs
  const [pan] = useState(() =>
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      onPanResponderTerminationRequest: () => false,
      onPanResponderGrant: () => {
        live.current.start = live.current.rect;
      },
      onPanResponderMove: (_, g) => {
        const { start: s, bounds: b } = live.current;
        let x1 = s.x, y1 = s.y, x2 = s.x + s.w, y2 = s.y + s.h;
        if (corner[1] === 'l') x1 = Math.min(Math.max(0, s.x + g.dx), x2 - MIN);
        else x2 = Math.max(Math.min(b.w, x2 + g.dx), x1 + MIN);
        if (corner[0] === 't') y1 = Math.min(Math.max(0, s.y + g.dy), y2 - MIN);
        else y2 = Math.max(Math.min(b.h, y2 + g.dy), y1 + MIN);
        live.current.onChange({ x: x1, y: y1, w: x2 - x1, h: y2 - y1 });
      },
    }),
  );

  const left = corner[1] === 'l' ? rect.x : rect.x + rect.w;
  const top = corner[0] === 't' ? rect.y : rect.y + rect.h;
  return (
    <View
      {...pan.panHandlers}
      role="button"
      accessibilityLabel={CORNER_LABEL[corner]}
      style={{
        position: 'absolute',
        left: left - 24,
        top: top - 24,
        width: 48,
        height: 48,
        alignItems: 'center',
        justifyContent: 'center',
        ...({ cursor: 'grab', touchAction: 'none' } as object), // web only
      }}
    >
      <View
        style={{
          width: 22,
          height: 22,
          borderRadius: 11,
          backgroundColor: c.surface,
          borderWidth: 4,
          borderColor: c.primary,
        }}
      />
    </View>
  );
}

export default function Crop() {
  const c = useColors();
  const [img, setImg] = useState<Picked | null>(session.picked);
  const [avail, setAvail] = useState(0);
  // The user's crop box, tied to the displayed size it was drawn at.
  const [drawn, setRect] = useState<{ key: string; r: Rect } | null>(null);
  const [busy, setBusy] = useState<'rotate' | 'read' | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!session.picked) router.replace('/');
    warmup();
  }, []);

  if (!img) return null;

  // Fit the photo into the available width, at most 460 px tall.
  const ar = img.width && img.height ? img.width / img.height : 3 / 4;
  const box = { w: avail, h: avail / ar };
  if (box.h > 460) {
    box.h = 460;
    box.w = 460 * ar;
  }
  const key = `${img.uri}|${box.w}|${box.h}`;
  const rect: Rect | null = !avail
    ? null
    : drawn?.key === key
      ? drawn.r
      : { x: box.w * 0.06, y: box.h * 0.06, w: box.w * 0.88, h: box.h * 0.88 };
  const onRect = (r: Rect) => setRect({ key, r });

  const go = async (full: boolean) => {
    setBusy('read');
    setFailed(false);
    try {
      const scale = img.width / (box.w || 1);
      const r = !full && rect ? { x: rect.x * scale, y: rect.y * scale, w: rect.w * scale, h: rect.h * scale } : null;
      session.upload = await prepareUpload(img, r);
    } catch {
      // The browser couldn't decode it (e.g. HEIC outside Safari): send as is; the server explains.
      session.upload = img;
    }
    router.replace('/processing');
  };

  const rotate = async () => {
    setBusy('rotate');
    try {
      const r = await rotate90(img);
      session.picked = r;
      setImg(r);
    } catch {
      setFailed(true);
    } finally {
      setBusy(null);
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <Header title="문제 영역 맞추기" back={{ label: '뒤로' }} />
      <Page>
        <T>
          문제 <T style={{ fontFamily: font.bold }}>하나만</T> 들어가도록 테두리의 네 모서리를 움직여 주세요.
        </T>
        <View onLayout={(e) => setAvail(e.nativeEvent.layout.width)} style={{ alignItems: 'center' }}>
          <View
            role="img"
            accessibilityLabel="찍은 사진. 테두리 안이 읽을 부분이에요."
            style={{ width: box.w, height: box.h, borderRadius: 12, overflow: 'hidden', backgroundColor: c.surface2 }}
          >
            <Image source={{ uri: img.uri }} style={{ width: box.w, height: box.h }} resizeMode="contain" />
            {rect && (
              <>
                {/* Dim outside the crop box */}
                <View pointerEvents="none" style={{ position: 'absolute', left: 0, top: 0, right: 0, height: rect.y, backgroundColor: 'rgba(0,0,0,0.45)' }} />
                <View pointerEvents="none" style={{ position: 'absolute', left: 0, top: rect.y + rect.h, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.45)' }} />
                <View pointerEvents="none" style={{ position: 'absolute', left: 0, top: rect.y, width: rect.x, height: rect.h, backgroundColor: 'rgba(0,0,0,0.45)' }} />
                <View pointerEvents="none" style={{ position: 'absolute', left: rect.x + rect.w, top: rect.y, right: 0, height: rect.h, backgroundColor: 'rgba(0,0,0,0.45)' }} />
                <View
                  pointerEvents="none"
                  style={{ position: 'absolute', left: rect.x, top: rect.y, width: rect.w, height: rect.h, borderWidth: 3, borderColor: c.primary }}
                />
                {(['tl', 'tr', 'bl', 'br'] as Corner[]).map((k) => (
                  <Handle key={k} corner={k} rect={rect} bounds={box} onChange={onRect} />
                ))}
              </>
            )}
          </View>
        </View>
        {failed && <Banner tone="error" title="사진을 돌리지 못했어요">다른 사진을 골라 주세요.</Banner>}
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
          <Button kind="secondary" icon="rotate" label="회전" onPress={rotate} style={{ flex: 1, minWidth: 120, paddingHorizontal: 12 }} />
          <Button kind="secondary" icon="fullFrame" label="사진 전체 쓰기" onPress={() => go(true)} style={{ flex: 1.4, minWidth: 160, paddingHorizontal: 12 }} />
        </View>
        <View style={{ gap: 12, marginTop: 'auto' }}>
          {busy ? (
            <View role="status" style={{ minHeight: 56, flexDirection: 'row', gap: 12, alignItems: 'center', justifyContent: 'center' }}>
              <ActivityIndicator color={c.primary} />
              <T>{busy === 'rotate' ? '사진을 돌리고 있어요' : '사진을 준비하고 있어요'}</T>
            </View>
          ) : (
            <Button kind="primary" label="이 문제 읽기" onPress={() => go(false)} />
          )}
          <Button kind="tertiary" label="다시 찍기" onPress={() => router.replace('/')} />
        </View>
      </Page>
    </View>
  );
}
