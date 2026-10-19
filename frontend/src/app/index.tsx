import * as ImagePicker from 'expo-image-picker';
import { router } from 'expo-router';
import Head from 'expo-router/head';
import { useState } from 'react';
import { Image, Platform, StyleSheet, Text, View } from 'react-native';

import { Body, Button, Card, Screen } from '@/components/ui';
import { Fonts, useTheme } from '@/constants/theme';
import { ApiError, createJob } from '@/lib/api';
import { setLastImage } from '@/lib/last-image';
import { prepareImage } from '@/lib/prepare-image';

type Source = 'camera' | 'library';

export default function Home() {
  const t = useTheme();
  const [preview, setPreview] = useState<string | null>(null);
  const [busy, setBusy] = useState<Source | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function pick(source: Source) {
    setError(null);
    // on web the camera opens through a file input, which needs no permission
    if (source === 'camera' && Platform.OS !== 'web') {
      const perm = await ImagePicker.requestCameraPermissionsAsync();
      if (!perm.granted) {
        setError('카메라 권한이 필요합니다. 설정에서 허용하거나 사진을 골라 주세요.');
        return;
      }
    }
    const options: ImagePicker.ImagePickerOptions = { mediaTypes: ['images'], quality: 1 };
    const result =
      source === 'camera'
        ? await ImagePicker.launchCameraAsync(options)
        : await ImagePicker.launchImageLibraryAsync(options);
    if (result.canceled || !result.assets?.length) return;
    const asset = result.assets[0];
    setPreview(asset.uri);
    setBusy(source);
    try {
      const image = await prepareImage(asset.uri, asset.width, asset.height);
      setLastImage(image);
      const id = await createJob(image);
      router.push(`/jobs/${id}`);
      setPreview(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '사진을 처리하지 못했습니다. 다른 사진으로 다시 시도해 주세요.');
    } finally {
      setBusy(null);
    }
  }

  return (
    <Screen>
      <Head>
        <title>MathTTS</title>
      </Head>
      <View style={styles.hero}>
        <Text style={[styles.eyebrow, { color: t.accent }]}>MathTTS</Text>
        <Text style={[styles.title, { color: t.text }]}>수학 문제를{'\n'}소리 내어 읽어 드립니다</Text>
        <Body muted>문제 하나가 잘 보이게 사진을 찍거나 고르세요. 글자와 수식을 읽어 한국어 음성으로 만들어 드립니다.</Body>
      </View>

      {preview && (
        <Image source={{ uri: preview }} style={[styles.preview, { borderColor: t.border }]} resizeMode="contain" />
      )}

      <View style={styles.actions}>
        <Button title="사진 찍기" onPress={() => pick('camera')} busy={busy === 'camera'} disabled={busy !== null} />
        <Button
          title="사진 고르기"
          variant="secondary"
          onPress={() => pick('library')}
          busy={busy === 'library'}
          disabled={busy !== null}
        />
      </View>

      {error && (
        <Card tone="danger">
          <Text style={{ color: t.danger, fontSize: 15, lineHeight: 22 }}>{error}</Text>
        </Card>
      )}

      <Text style={[styles.note, { color: t.textSecondary }]}>
        올린 사진과 결과는 24시간 뒤 삭제됩니다.
      </Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  hero: { gap: 12, paddingTop: 24 },
  eyebrow: { fontSize: 14, fontWeight: '700', letterSpacing: 1, fontFamily: Fonts.sans },
  title: { fontSize: 30, lineHeight: 40, fontWeight: '700', fontFamily: Fonts.sans },
  preview: { width: '100%', height: 220, borderRadius: 14, borderWidth: 1 },
  actions: { gap: 12 },
  note: { fontSize: 13, lineHeight: 19, textAlign: 'center', fontFamily: Fonts.sans },
});
