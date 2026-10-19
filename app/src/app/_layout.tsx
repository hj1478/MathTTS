import {
  IBMPlexSansKR_400Regular,
  IBMPlexSansKR_500Medium,
  IBMPlexSansKR_600SemiBold,
  IBMPlexSansKR_700Bold,
  useFonts,
} from '@expo-google-fonts/ibm-plex-sans-kr';
import { setAudioModeAsync } from 'expo-audio';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useState } from 'react';
import { AppState, Platform } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { warmup } from '@/lib/api';
import { restoreSession } from '@/lib/store';
import { useColors, useScheme } from '@/lib/theme';

// Korean wraps between words, not syllables (as in the designs).
if (Platform.OS === 'web' && typeof document !== 'undefined') {
  const style = document.createElement('style');
  style.textContent = 'body{word-break:keep-all;overflow-wrap:break-word}';
  document.head.appendChild(style);
}

export default function RootLayout() {
  // Render with system fonts if the font files fail (Tokens.dc.html §2).
  const [loaded, error] = useFonts({
    IBMPlexSansKR_400Regular,
    IBMPlexSansKR_500Medium,
    IBMPlexSansKR_600SemiBold,
    IBMPlexSansKR_700Bold,
  });
  const c = useColors();
  const scheme = useScheme();
  // The photo, job and results of the current flow, so a refresh continues it.
  const [restored, setRestored] = useState(false);

  useEffect(() => {
    restoreSession().finally(() => setRestored(true));
    // A GPU worker takes ~30 s to start; begin while the user picks a photo.
    warmup();
    setAudioModeAsync({ playsInSilentMode: true }).catch(() => {});
    // Back from the background (or a hidden browser tab): the worker stops
    // 90 s after its last job. warmup() skips it if one went out in the last minute.
    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'active') warmup();
    });
    return () => sub.remove();
  }, []);

  if ((!loaded && !error) || !restored) return null;
  return (
    <SafeAreaProvider>
      <StatusBar style={scheme === 'dark' ? 'light' : 'dark'} />
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: c.bg } }} />
    </SafeAreaProvider>
  );
}
