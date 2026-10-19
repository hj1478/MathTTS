import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { AppState } from 'react-native';

import { useTheme } from '@/constants/theme';
import { warmup } from '@/lib/api';

// The backend's worker stays up 90 s after its last job; a foreground return
// sooner than this does not need another warmup.
const REWARM_AFTER_MS = 60_000;

export default function RootLayout() {
  const t = useTheme();

  useEffect(() => {
    // As soon as the app or page opens, before the user picks a photo: a GPU
    // worker starts while they do (docs/API.md, POST /warmup).
    let last = Date.now();
    warmup();
    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'active' && Date.now() - last > REWARM_AFTER_MS) {
        last = Date.now();
        warmup();
      }
    });
    return () => sub.remove();
  }, []);

  return (
    <>
      <StatusBar style="auto" />
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: t.background } }} />
    </>
  );
}
