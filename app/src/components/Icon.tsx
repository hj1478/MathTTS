// The stroke icons used across design/ui, 24×24 grid.
import { Platform } from 'react-native';
import Svg, { Circle, Path, Rect } from 'react-native-svg';

// Decorative: hidden from screen readers. react-native-svg passes these props to the DOM on web.
const hidden =
  Platform.OS === 'web'
    ? { 'aria-hidden': true }
    : { accessibilityElementsHidden: true, importantForAccessibility: 'no-hide-descendants' as const };

const P = (d: string, fill?: boolean) => <Path d={d} fill={fill ? 'currentColor' : 'none'} />;

const shapes = {
  camera: (
    <>
      {P('M3 8a2 2 0 0 1 2-2h2.5l1.5-2h6l1.5 2H19a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z')}
      <Circle cx={12} cy={13} r={4} fill="none" />
    </>
  ),
  gallery: (
    <>
      <Rect x={3} y={4} width={18} height={16} rx={2} fill="none" />
      <Circle cx={9} cy={10} r={2} fill="none" />
      {P('M21 16l-5-5-9 9')}
    </>
  ),
  clock: (
    <>
      <Circle cx={12} cy={12} r={9} fill="none" />
      {P('M12 7v5l3 2')}
    </>
  ),
  bookmark: P('M6 3h12v18l-6-4-6 4z'),
  bookmarkFilled: P('M6 3h12v18l-6-4-6 4z', true),
  expand: P('M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7'),
  back: P('M15 18l-6-6 6-6'),
  chevron: P('M9 6l6 6-6 6'),
  trash: P('M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13'),
  close: P('M6 6l12 12M18 6L6 18'),
  check: P('M5 12l5 5 9-10'),
  rewind: (
    <>
      {P('M11 18l-7-6 7-6z')}
      {P('M20 18l-7-6 7-6z')}
    </>
  ),
  play: <Path d="M8 5v14l11-7z" fill="currentColor" stroke="none" />,
  pause: (
    <>
      <Rect x={6} y={5} width={4} height={14} rx={1} fill="currentColor" stroke="none" />
      <Rect x={14} y={5} width={4} height={14} rx={1} fill="currentColor" stroke="none" />
    </>
  ),
  restart: (
    <>
      {P('M3 12a9 9 0 1 0 3-6.7L3 8')}
      {P('M3 3v5h5')}
    </>
  ),
  rotate: (
    <>
      {P('M21 12a9 9 0 1 1-3-6.7L21 8')}
      {P('M21 3v5h-5')}
    </>
  ),
  fullFrame: P('M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5'),
  speaker: (
    <>
      {P('M4 9v6h4l5 4V5L8 9z')}
      {P('M16.5 8.5a5 5 0 0 1 0 7')}
    </>
  ),
  mute: (
    <>
      {P('M4 9v6h4l5 4V5L8 9z')}
      {P('M17 9l5 5M22 9l-5 5')}
    </>
  ),
  info: (
    <>
      <Circle cx={12} cy={12} r={9} fill="none" />
      {P('M12 11v6M12 7.5v.5')}
    </>
  ),
  error: (
    <>
      <Circle cx={12} cy={12} r={9} fill="none" />
      {P('M12 7v6M12 16.5v.5')}
    </>
  ),
  offline: (
    <>
      {P('M2 2l20 20M8.5 16.5a5 5 0 0 1 7 0M5 12.5a10 10 0 0 1 4.2-2.4M19 12.5a10 10 0 0 0-2.3-1.6M2 8.8a15 15 0 0 1 4.3-2.6M22 8.8A15 15 0 0 0 11 5')}
      {P('M12 20h.01')}
    </>
  ),
  upload: P('M12 16V4M7 9l5-5 5 5M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3'),
  plus: P('M12 5v14M5 12h14'),
  notImage: (
    <>
      {P('M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z')}
      {P('M14 3v5h5M10 12l4 4M14 12l-4 4')}
    </>
  ),
};

export type IconName = keyof typeof shapes;

export function Icon({
  name,
  size = 22,
  color,
  strokeWidth = 2,
}: {
  name: IconName;
  size?: number;
  color: string;
  strokeWidth?: number;
}) {
  return (
    <Svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      color={color}
      stroke={color}
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      {...hidden}
    >
      {shapes[name]}
    </Svg>
  );
}
