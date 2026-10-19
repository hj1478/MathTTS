// 4 결과 (Result.dc.html, ResultDark, ResultLargeText), D2 데스크톱 결과,
// and E1 음성 사용량 초과 (QuotaReached.dc.html) when there is no audio.
import { useAudioPlayer, useAudioPlayerStatus } from 'expo-audio';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { AccessibilityInfo, Image, Modal, Platform, Pressable, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Icon } from '@/components/Icon';
import { MathText } from '@/components/MathText';
import { Player, Spoken, type ViewRef } from '@/components/Player';
import { Banner, Button, Card, H2, Header, HeaderLink, Page, PROTOTYPE_NOTE, T } from '@/components/ui';
import { when } from '@/lib/format';
import { getReading, isSaved, loadSpeed, removeReading, saveReading, session, storeSpeed, type Reading } from '@/lib/store';
import { useColors, useWide } from '@/lib/theme';

function NoAudio({ r, onRetry }: { r: Reading; onRetry: () => void }) {
  const copy = {
    quota_reached: [
      '지금은 음성을 들을 수 없어요',
      '음성 사용량이 잠시 다 찼어요. 문제는 정상적으로 읽었으니 아래 글로 확인해 주세요. 화면 읽기 기능으로도 들을 수 있어요.',
      '음성 다시 시도',
    ],
    failed: [
      '음성을 만들지 못했어요',
      '문제는 정상적으로 읽었으니 아래 글로 확인해 주세요. 화면 읽기 기능으로도 들을 수 있어요.',
      '음성 다시 시도',
    ],
    skipped: [
      '이 문제는 음성으로 만들지 않았어요',
      '수식 일부를 확실하게 읽지 못해서, 틀린 소리를 들려 드리지 않으려고 음성을 만들지 않았어요. 아래 글과 사진을 비교해 주세요.',
      null,
    ],
    expired: [
      '음성 보관 기간이 지났어요',
      '음성은 24시간 동안만 보관돼요. 글은 아래에서 볼 수 있고, 같은 사진으로 다시 읽으면 음성을 다시 들을 수 있어요.',
      '다시 읽기',
    ],
    ready: ['음성을 불러오지 못했어요', '아래 글로 확인해 주세요.', null],
  }[r.audioStatus];
  return (
    <Banner
      tone="info"
      icon="mute"
      title={copy[0]!}
      action={
        copy[2] && (
          <View style={{ alignSelf: 'flex-start', marginTop: 4 }}>
            <Button kind="secondary" icon="restart" label={copy[2]} onPress={onRetry} />
          </View>
        )
      }
    >
      {copy[1]!}
    </Banner>
  );
}

export default function Result() {
  const c = useColors();
  const wide = useWide();
  const insets = useSafeAreaInsets();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [r, setR] = useState<Reading | null | undefined>(session.readings.get(id));
  const [saved, setSaved] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [zoom, setZoom] = useState(false);
  const playRef = useRef<ViewRef>(null);

  useEffect(() => {
    getReading(id).then((x) => setR(x ?? null));
    isSaved(id).then(setSaved);
    loadSpeed().then(setSpeed);
  }, [id]);

  const hasAudio = !!r && r.audioStatus === 'ready' && !!r.audioUrl;
  const player = useAudioPlayer(hasAudio ? r!.audioUrl : null, { updateInterval: 250 });
  const status = useAudioPlayerStatus(player);

  useEffect(() => {
    player.setPlaybackRate(speed, 'high');
  }, [player, speed, status.isLoaded]);

  // "문제를 다 읽었어요. 재생 버튼", then focus play. No autoplay: it would talk over the screen reader.
  useEffect(() => {
    if (!r) return;
    const t = setTimeout(() => {
      if (Platform.OS === 'web') (playRef.current as unknown as HTMLElement | null)?.focus?.();
      else {
        AccessibilityInfo.announceForAccessibility(hasAudio ? '문제를 다 읽었어요. 재생 버튼' : '문제를 다 읽었어요');
        if (playRef.current) AccessibilityInfo.sendAccessibilityEvent(playRef.current, 'focus');
      }
    }, 400);
    return () => clearTimeout(t);
  }, [r, hasAudio]);

  if (r === null) {
    return (
      <View style={{ flex: 1, backgroundColor: c.bg }}>
        <Header title="읽은 결과" back={{ label: '처음 화면으로', onPress: () => router.replace('/') }} />
        <Page>
          <Banner tone="error" title="결과를 찾을 수 없어요">
            기록에서 지워졌거나 다른 기기에서 저장한 결과예요.
          </Banner>
          <Button kind="primary" icon="plus" label="새 문제" onPress={() => router.replace('/')} />
        </Page>
      </View>
    );
  }
  if (!r) return null;

  const toggleSave = async () => {
    if (saved) await removeReading(r.id);
    else await saveReading(r);
    setSaved(!saved);
    if (Platform.OS !== 'web') AccessibilityInfo.announceForAccessibility(saved ? '기록에서 뺐어요' : '저장됨');
  };
  const again = () => {
    session.upload = { uri: r.imageUri, width: r.imageWidth, height: r.imageHeight, mimeType: 'image/jpeg', name: 'photo.jpg' };
    router.replace('/processing');
  };
  const pickSpeed = (v: number) => {
    setSpeed(v);
    storeSpeed(v);
  };

  const listen = hasAudio ? (
    <Player ref={playRef} player={player} status={status} speed={speed} onSpeed={pickSpeed} />
  ) : (
    <NoAudio r={r} onRetry={again} />
  );

  const note = <Banner tone="note">{PROTOTYPE_NOTE}</Banner>;

  const spoken = (
    <Card style={{ borderRadius: 20 }}>
      <View style={{ gap: 4 }}>
        <H2>{hasAudio ? '읽어 주는 문장' : '읽어 줄 문장'}</H2>
        {hasAudio && (
          <T v="caption" muted>
            지금 읽는 부분에 배경과 밑줄이 표시돼요.
          </T>
        )}
      </View>
      <Spoken text={r.spokenText} time={status.currentTime} duration={status.duration} big={wide} />
    </Card>
  );

  const compare = (
    <Card style={{ borderRadius: 20 }}>
      <View style={{ gap: 4 }}>
        <H2>사진과 비교하기</H2>
        <T v="caption" muted>
          수식과 숫자가 같은지 살펴보세요.
        </T>
      </View>
      <View style={{ gap: 8 }}>
        <Pressable onPress={() => setZoom(true)} accessibilityLabel="원본 사진, 크게 보기" role="button">
          <Image
            source={{ uri: r.imageUri }}
            resizeMode="contain"
            style={{ width: '100%', aspectRatio: r.imageWidth && r.imageHeight ? Math.max(r.imageWidth / r.imageHeight, 1.2) : 1.6, borderRadius: 12, backgroundColor: c.surface2 }}
          />
        </Pressable>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
          <T v="caption" muted>
            원본 사진
          </T>
          <Button kind="tertiary" icon="expand" label="크게 보기" onPress={() => setZoom(true)} />
        </View>
      </View>
      <View style={{ height: 1, backgroundColor: c.border }} />
      <View style={{ gap: 8 }}>
        <T v="section" role="heading" aria-level={3}>
          읽은 문제
        </T>
        <MathText text={r.normalizedText} label={r.spokenText} big={wide} />
        <View style={{ flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 4 }}>
          <T muted>사진과 다른가요?</T>
          <Button kind="tertiary" label={wide ? '다른 사진 올리기' : '다시 찍기'} onPress={() => router.replace('/')} />
        </View>
      </View>
    </Card>
  );

  const actions = (
    <>
      <Button
        kind="secondary"
        icon={saved ? 'bookmarkFilled' : 'bookmark'}
        label={saved ? '저장됨' : '기록에 저장'}
        aria-pressed={saved}
        accessibilityState={{ checked: saved }}
        onPress={toggleSave}
        style={{ flex: 1, minWidth: 150 }}
      />
      <Button kind="primary" icon="plus" label="새 문제" onPress={() => router.replace('/')} style={{ flex: 1, minWidth: 150 }} />
    </>
  );

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      {wide ? (
        <Header brand right={<View style={{ flexDirection: 'row' }}><HeaderLink icon="plus" label="새 문제" href="/" /><HeaderLink icon="clock" label="기록" href="/history" /></View>} />
      ) : (
        <Header
          title="읽은 결과"
          back={{ label: '처음 화면으로', onPress: () => router.replace('/') }}
          right={<HeaderLink icon="clock" label="기록" href="/history" />}
        />
      )}
      {wide ? (
        <Page>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 16 }}>
            <View style={{ flex: 1, minWidth: 240, gap: 2 }}>
              <T v="title" role="heading" aria-level={1}>
                읽은 결과
              </T>
              <T muted>{when(r.createdAt)}</T>
            </View>
            <View style={{ flexDirection: 'row', gap: 12, minWidth: 340 }}>{actions}</View>
          </View>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 24, alignItems: 'flex-start' }}>
            <View style={{ flexGrow: 999, flexShrink: 1, flexBasis: 560, gap: 24 }}>
              {listen}
              {spoken}
            </View>
            <View style={{ flexGrow: 1, flexShrink: 1, flexBasis: 320, gap: 24 }}>
              {note}
              {compare}
            </View>
          </View>
        </Page>
      ) : (
        <Page footer={actions}>
          {listen}
          {note}
          {spoken}
          {compare}
        </Page>
      )}

      <Modal visible={zoom} onRequestClose={() => setZoom(false)} animationType="none" transparent={false}>
        <View style={{ flex: 1, backgroundColor: '#000', paddingTop: insets.top, paddingBottom: insets.bottom }}>
          <View style={{ flexDirection: 'row', justifyContent: 'flex-end', padding: 8 }}>
            <Pressable
              role="button"
              accessibilityLabel="닫기"
              onPress={() => setZoom(false)}
              style={{ width: 48, height: 48, alignItems: 'center', justifyContent: 'center' }}
            >
              <Icon name="close" size={28} color="#FFFFFF" />
            </Pressable>
          </View>
          <Image source={{ uri: r.imageUri }} resizeMode="contain" style={{ flex: 1 }} accessibilityLabel="원본 사진" />
        </View>
      </Modal>
    </View>
  );
}
