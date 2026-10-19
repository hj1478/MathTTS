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
import { useEffect } from 'react';
import { Platform, useColorScheme } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { warmup } from '@/lib/api';
import { useColors } from '@/lib/theme';

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
  const scheme = useColorScheme();

  useEffect(() => {
    // A GPU worker takes ~30 s to start; begin while the user picks a photo.
    warmup();
    setAudioModeAsync({ playsInSilentMode: true }).catch(() => {});
  }, []);

  if (!loaded && !error) return null;
  return (
    <SafeAreaProvider>
      <StatusBar style={scheme === 'dark' ? 'light' : 'dark'} />
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: c.bg } }} />
    </SafeAreaProvider>
  );
}
