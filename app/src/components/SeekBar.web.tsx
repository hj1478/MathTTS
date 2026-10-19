// Web seek bar: a real <input type="range"> so keyboards and screen readers get it for free.
import { useColors } from '@/lib/theme';
import type { SeekBarProps } from './SeekBar';

export function SeekBar({ value, max, onSeek, valueText }: SeekBarProps) {
  const c = useColors();
  return (
    <input
      type="range"
      min={0}
      max={max || 0}
      step={0.1}
      value={Math.min(value, max || 0)}
      onChange={(e) => onSeek(Number(e.currentTarget.value))}
      aria-label="재생 위치"
      aria-valuetext={valueText}
      style={{ width: '100%', height: 48, margin: 0, accentColor: c.primary, cursor: 'pointer' }}
    />
  );
}
