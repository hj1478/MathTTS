// Native seek bar: 48 px touch height, adjustable for screen readers in 5 s steps.
import { useEffect, useRef, useState } from 'react';
import { PanResponder, View } from 'react-native';

import { useColors } from '@/lib/theme';

export interface SeekBarProps {
  value: number;
  max: number;
  onSeek: (t: number) => void;
  valueText: string;
}

export function SeekBar({ value, max, onSeek, valueText }: SeekBarProps) {
  const c = useColors();
  const [width, setWidth] = useState(1);
  const [drag, setDrag] = useState<number | null>(null);
  const ref = useRef({ width, max, onSeek });
  useEffect(() => {
    ref.current = { width, max, onSeek };
  });

  // The handlers read `ref` when a gesture happens, never during render.
  // eslint-disable-next-line react-hooks/refs
  const [pan] = useState(() => {
    const at = (x: number) => Math.min(1, Math.max(0, x / ref.current.width)) * ref.current.max;
    return PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      onPanResponderGrant: (e) => setDrag(at(e.nativeEvent.locationX)),
      onPanResponderMove: (e) => setDrag(at(e.nativeEvent.locationX)),
      onPanResponderRelease: (e) => {
        ref.current.onSeek(at(e.nativeEvent.locationX));
        setDrag(null);
      },
      onPanResponderTerminate: () => setDrag(null),
    });
  });

  const t = drag ?? value;
  const frac = max > 0 ? Math.min(1, t / max) : 0;
  return (
    <View
      accessible
      accessibilityRole="adjustable"
      accessibilityLabel="재생 위치"
      accessibilityValue={{ text: valueText }}
      accessibilityActions={[{ name: 'increment' }, { name: 'decrement' }]}
      onAccessibilityAction={(e) =>
        onSeek(Math.min(max, Math.max(0, value + (e.nativeEvent.actionName === 'increment' ? 5 : -5))))
      }
      onLayout={(e) => setWidth(e.nativeEvent.layout.width || 1)}
      style={{ height: 48, justifyContent: 'center' }}
      {...pan.panHandlers}
    >
      <View pointerEvents="none" style={{ height: 6, borderRadius: 3, backgroundColor: c.surface2 }}>
        <View style={{ width: `${frac * 100}%`, height: 6, borderRadius: 3, backgroundColor: c.primary }} />
      </View>
      <View
        pointerEvents="none"
        style={{
          position: 'absolute',
          left: frac * width - 12,
          width: 24,
          height: 24,
          borderRadius: 12,
          backgroundColor: c.primary,
          borderWidth: 3,
          borderColor: c.surface,
        }}
      />
    </View>
  );
}
