import { useAudioPlayer, useAudioPlayerStatus } from 'expo-audio';
import { useEffect } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { Button } from '@/components/ui';
import { Fonts, useTheme } from '@/constants/theme';

function clock(s: number) {
  const total = Math.max(0, Math.floor(s || 0));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}

/** Plays the job's MP3 (GET /audio/{id}). */
export function AudioPlayer({ url }: { url: string }) {
  const t = useTheme();
  const player = useAudioPlayer(url);
  const status = useAudioPlayerStatus(player);

  useEffect(() => {
    if (status.didJustFinish) player.seekTo(0);
  }, [status.didJustFinish, player]);

  const progress = status.duration > 0 ? Math.min(1, status.currentTime / status.duration) : 0;

  return (
    <View style={styles.wrap}>
      <Button
        title={status.playing ? '일시정지' : '듣기'}
        onPress={() => (status.playing ? player.pause() : player.play())}
        busy={!status.isLoaded}
      />
      <View style={[styles.track, { backgroundColor: t.accentSoft }]}>
        <View style={[styles.fill, { backgroundColor: t.accent, width: `${progress * 100}%` }]} />
      </View>
      {status.duration > 0 && (
        <Text style={[styles.time, { color: t.textSecondary }]}>
          {clock(status.currentTime)} / {clock(status.duration)}
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 10 },
  track: { height: 6, borderRadius: 3, overflow: 'hidden' },
  fill: { height: 6 },
  time: { fontSize: 13, fontVariant: ['tabular-nums'], textAlign: 'right', fontFamily: Fonts.sans },
});
