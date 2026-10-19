import { router, useLocalSearchParams } from 'expo-router';
import Head from 'expo-router/head';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { AudioPlayer } from '@/components/audio-player';
import { Body, Button, Card, Label, Screen } from '@/components/ui';
import { Fonts, useTheme, type Theme } from '@/constants/theme';
import { ApiError, createJob, warmup, type StageName, type StageState } from '@/lib/api';
import { getLastImage } from '@/lib/last-image';
import { GIVE_UP_AFTER_S, jobAgeS, useJob } from '@/lib/use-job';

const STAGE_LABELS: Record<StageName, string> = {
  ocr: '글자 인식',
  normalize: '수식 정리',
  speech: '읽을 문장 만들기',
  tts: '음성 만들기',
};

function clock(s: number) {
  const total = Math.floor(s);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}

/** Re-renders every second, for the elapsed-time display. */
function useTick(active: boolean) {
  const [, setTick] = useState(0);
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(timer);
  }, [active]);
}

export default function JobScreen() {
  const t = useTheme();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { job, error, offline, gaveUp } = useJob(id);
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);

  const waiting = !error && !gaveUp && (!job || job.status === 'queued' || job.status === 'running');
  useTick(waiting);

  async function retry() {
    const image = getLastImage();
    if (!image) {
      router.replace('/'); // the photo is gone (page refreshed): pick it again
      return;
    }
    setRetrying(true);
    setRetryError(null);
    try {
      warmup();
      const next = await createJob(image);
      router.replace(`/jobs/${next}`);
    } catch (e) {
      setRetryError(e instanceof ApiError ? e.message : '다시 시도하지 못했습니다.');
    } finally {
      setRetrying(false);
    }
  }

  const retryLabel = getLastImage() ? '다시 시도' : '사진 다시 고르기';
  const elapsed = job ? jobAgeS(job) : 0;
  const ocrText = job?.stages?.ocr?.text;
  const speechText = job?.stages?.speech?.text;

  return (
    <Screen>
      <Head>
        <title>MathTTS · 결과</title>
      </Head>
      <Pressable accessibilityRole="link" onPress={() => router.replace('/')} hitSlop={8}>
        <Text style={[styles.back, { color: t.accent }]}>← 새 사진</Text>
      </Pressable>

      {error ? (
        <Card tone="danger">
          <Text style={[styles.alert, { color: t.danger }]}>{error.message}</Text>
          <Button title="처음으로" onPress={() => router.replace('/')} />
        </Card>
      ) : gaveUp ? (
        <Card tone="danger">
          <Text style={[styles.alertTitle, { color: t.danger }]}>서버가 응답하지 않습니다</Text>
          <Text style={[styles.alert, { color: t.danger }]}>
            {Math.round(GIVE_UP_AFTER_S / 60)}분을 기다렸지만 처리가 끝나지 않았습니다. 잠시 후 다시 시도해 주세요.
          </Text>
          <Button title={retryLabel} onPress={retry} busy={retrying} />
        </Card>
      ) : !job || job.status === 'queued' ? (
        <Card>
          <View style={styles.row}>
            <ActivityIndicator color={t.accent} />
            <Text style={[styles.statusTitle, { color: t.text }]}>서버를 준비하고 있습니다</Text>
            <Text style={[styles.elapsed, { color: t.textSecondary }]}>{clock(elapsed)}</Text>
          </View>
          <Body muted>
            문제를 읽는 GPU 서버를 켜는 중입니다. 보통 30초 안팎이면 시작하지만, 드물게 몇 분까지 걸릴 수 있습니다. 이
            화면을 열어 둔 채로 기다려 주세요.
          </Body>
        </Card>
      ) : null}

      {offline && waiting && <Text style={[styles.note, { color: t.textSecondary }]}>연결이 불안정합니다. 계속 확인하고 있습니다…</Text>}

      {job && job.status !== 'queued' && !gaveUp && (
        <Card>
          {(Object.keys(STAGE_LABELS) as StageName[]).map((name) => (
            <StageRow key={name} label={STAGE_LABELS[name]} state={job.stage_status[name]} t={t} />
          ))}
          {job.status === 'running' && (
            <Text style={[styles.note, { color: t.textSecondary, textAlign: 'left' }]}>경과 {clock(elapsed)}</Text>
          )}
        </Card>
      )}

      {job?.status === 'failed' && job.error && (
        <Card tone="danger">
          <Text style={[styles.alert, { color: t.danger }]}>{job.error.message}</Text>
          <Button title={retryLabel} onPress={retry} busy={retrying} />
        </Card>
      )}
      {retryError && <Text style={[styles.alert, { color: t.danger }]}>{retryError}</Text>}

      {job?.status === 'done' && job.audio && (
        <Card>
          <Label>음성</Label>
          {job.audio.status === 'ready' && job.audio.url ? (
            <AudioPlayer url={job.audio.url} />
          ) : (
            <Body muted>{job.audio.message}</Body>
          )}
        </Card>
      )}

      {speechText && (
        <Card>
          <Label>읽는 문장</Label>
          <Body>{speechText}</Body>
        </Card>
      )}

      {ocrText && (
        <Card>
          <Label>인식한 문제</Label>
          <Body mono>{ocrText.trim()}</Body>
        </Card>
      )}
    </Screen>
  );
}

function StageRow({ label, state, t }: { label: string; state: StageState; t: Theme }) {
  const icon = { done: '✓', failed: '✕', skipped: '–', pending: '○', running: '' }[state];
  const color = state === 'failed' ? t.danger : state === 'pending' || state === 'skipped' ? t.textSecondary : t.text;
  return (
    <View style={styles.row}>
      <View style={styles.icon}>
        {state === 'running' ? (
          <ActivityIndicator size="small" color={t.accent} />
        ) : (
          <Text style={{ color: state === 'done' ? t.accent : color, fontSize: 16, fontWeight: '700' }}>{icon}</Text>
        )}
      </View>
      <Text style={[styles.stage, { color }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  back: { fontSize: 16, fontWeight: '600', fontFamily: Fonts.sans },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  icon: { width: 22, alignItems: 'center' },
  stage: { fontSize: 16, fontFamily: Fonts.sans },
  statusTitle: { flex: 1, fontSize: 17, fontWeight: '600', fontFamily: Fonts.sans },
  elapsed: { fontSize: 17, fontVariant: ['tabular-nums'], fontFamily: Fonts.sans },
  alertTitle: { fontSize: 17, fontWeight: '700', fontFamily: Fonts.sans },
  alert: { fontSize: 15, lineHeight: 22, fontFamily: Fonts.sans },
  note: { fontSize: 13, textAlign: 'center', fontFamily: Fonts.sans },
});
