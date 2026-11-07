// A page with several numbered problems: the photo with the current problem
// boxed, and 이전 / 다음 to step through them. The boxes come from the OCR's
// layout (backend/problems.py), as fractions of the photo.
import { useState } from 'react';
import { Image, Pressable, Text, View, type LayoutChangeEvent } from 'react-native';

import type { Problem } from '@/lib/store';
import { font, useColors } from '@/lib/theme';
import { Button, T } from './ui';

const PAD = 4; // px around a box, so the outline doesn't sit on the text

/**
 * The photo fitted inside its container (contain), with every problem's
 * area outlined and the current one filled. Tapping an area picks that problem.
 * `maxHeight` caps the height when the container itself has no fixed height.
 */
export function ProblemPhoto({
  uri,
  aspect,
  problems,
  cur,
  onPick,
  maxHeight,
  fill,
}: {
  uri: string;
  aspect: number; // width / height
  problems: Problem[];
  cur: number;
  onPick: (i: number) => void;
  maxHeight?: number;
  fill?: boolean; // take the parent's whole area (the zoom view)
}) {
  const c = useColors();
  const [box, setBox] = useState<{ w: number; h: number } | null>(null);
  const onLayout = (e: LayoutChangeEvent) => {
    const { width, height } = e.nativeEvent.layout;
    setBox({ w: width, h: height });
  };
  let w = 0;
  let h = 0;
  if (box) {
    const limitH = fill ? box.h : (maxHeight ?? Infinity);
    w = Math.min(box.w, limitH * aspect);
    h = w / aspect;
  }
  return (
    <View onLayout={onLayout} style={fill ? { flex: 1, alignItems: 'center', justifyContent: 'center' } : { width: '100%', alignItems: 'center' }}>
      {box && w > 0 && (
        <View style={{ width: w, height: h }}>
          <Image source={{ uri }} resizeMode="stretch" style={{ width: w, height: h, borderRadius: 8 }} accessibilityLabel="원본 사진" />
          {problems.map((p, i) =>
            p.boxes.map(([x0, y0, x1, y1], k) => {
              const on = i === cur;
              return (
                <Pressable
                  key={`${i}-${k}`}
                  role="button"
                  accessibilityLabel={`${p.label}번 문제 듣기`}
                  aria-current={on || undefined}
                  accessibilityState={{ selected: on }}
                  // only the first box of each problem is a separate stop for screen readers
                  accessible={k === 0}
                  onPress={() => onPick(i)}
                  style={{
                    position: 'absolute',
                    left: Math.max(0, x0 * w - PAD),
                    top: Math.max(0, y0 * h - PAD),
                    width: Math.min(w, (x1 - x0) * w + 2 * PAD),
                    height: Math.min(h, (y1 - y0) * h + 2 * PAD),
                    borderRadius: 6,
                    borderWidth: on ? 3 : 1.5,
                    borderStyle: on ? 'solid' : 'dashed',
                    borderColor: on ? c.hlLine : c.borderStrong,
                    backgroundColor: on ? 'rgba(255, 229, 138, 0.35)' : 'transparent',
                  }}
                >
                  {k === 0 && (
                    <View
                      style={{
                        position: 'absolute',
                        left: -2,
                        top: -2,
                        minWidth: 24,
                        paddingHorizontal: 5,
                        borderRadius: 6,
                        backgroundColor: on ? c.hlLine : c.borderStrong,
                      }}
                    >
                      <Text style={{ fontFamily: font.bold, fontSize: 13, lineHeight: 20, color: '#FFFFFF', textAlign: 'center' }}>
                        {p.label}
                      </Text>
                    </View>
                  )}
                </Pressable>
              );
            }),
          )}
        </View>
      )}
    </View>
  );
}

/** "3번 문제 · 2 / 5" with 이전 / 다음. */
export function ProblemNav({
  problems,
  cur,
  onPick,
  finished,
}: {
  problems: Problem[];
  cur: number;
  onPick: (i: number) => void;
  finished: boolean; // the current problem has played to the end: 다음 is the main action
}) {
  const p = problems[cur]!;
  const last = cur === problems.length - 1;
  return (
    <View style={{ gap: 12 }}>
      <View style={{ flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', gap: 8 }}>
        <T v="section" role="heading" aria-level={2}>
          {p.label}번 문제
        </T>
        <T muted style={{ fontVariant: ['tabular-nums'] }} accessibilityLabel={`${problems.length}문제 중 ${cur + 1}번째`}>
          {cur + 1} / {problems.length}
        </T>
      </View>
      <View style={{ flexDirection: 'row', gap: 12 }}>
        <Button
          kind="secondary"
          icon="back"
          label="이전 문제"
          disabled={cur === 0}
          aria-disabled={cur === 0 || undefined}
          onPress={() => onPick(cur - 1)}
          style={{ flex: 1, opacity: cur === 0 ? 0.4 : 1 }}
        />
        <Button
          kind={finished && !last ? 'primary' : 'secondary'}
          icon="chevron"
          label="다음 문제"
          disabled={last}
          aria-disabled={last || undefined}
          onPress={() => onPick(cur + 1)}
          style={{ flex: 1, opacity: last ? 0.4 : 1 }}
        />
      </View>
    </View>
  );
}
