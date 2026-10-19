// Native has no drag and drop; the zone is just its contents.
import type { ReactNode } from 'react';
import { View } from 'react-native';

export function DropZone({ children }: { children: ReactNode; onFile: (f: File) => void }) {
  return <View>{children}</View>;
}
