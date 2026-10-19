// Desktop drop zone (DesktopHome.dc.html): drop a photo anywhere in the dashed box.
import { useState, type ReactNode } from 'react';

import { useColors } from '@/lib/theme';

export function DropZone({ children, onFile }: { children: ReactNode; onFile: (f: File) => void }) {
  const c = useColors();
  const [over, setOver] = useState(false);
  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        const f = e.dataTransfer.files?.[0];
        if (f) onFile(f);
      }}
      style={{
        display: 'flex',
        flexDirection: 'column',
        borderRadius: 24,
        border: `2px dashed ${over ? c.primary : c.borderStrong}`,
        background: over ? c.primarySoft : c.surface,
      }}
    >
      {children}
    </div>
  );
}
