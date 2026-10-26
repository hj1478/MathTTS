// Native opens the system camera through expo-image-picker; nothing to render.
export function WebCamera(_: {
  onCapture: (f: File) => void;
  onProblem: (kind: 'denied' | 'no_camera') => void;
  onClose: () => void;
}) {
  return null;
}
