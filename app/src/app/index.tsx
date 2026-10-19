// 1 홈 · 촬영 (Main.dc.html), D1 데스크톱 홈, and the upload-rejected / offline states (E3, E4).
import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useCallback, useState } from 'react';
import { Platform, View } from 'react-native';

import { DropZone } from '@/components/DropZone';
import { HistoryRow } from '@/components/HistoryRow';
import { Icon } from '@/components/Icon';
import { Banner, Button, Card, H2, Header, HeaderLink, Page, T } from '@/components/ui';
import { warmup } from '@/lib/api';
import { megabytes } from '@/lib/format';
import { fromFile, pickPhoto, type PickProblem, type PickResult } from '@/lib/image';
import { listHistory, session, type Reading } from '@/lib/store';
import { font, useColors, useWide } from '@/lib/theme';
import { useOnline } from '@/lib/useOnline';

/** A rejected upload: picked locally, or the server's 4xx sent back from processing. */
type Problem = PickProblem | { kind: 'server'; code: string; message: string };

function ProblemBanner({ p }: { p: Problem }) {
  switch (p.kind) {
    case 'too_large':
      return (
        <Banner tone="error" title="사진이 너무 커요">
          {`선택한 사진은 ${megabytes(p.size)}예요. 5 MB 이하인 사진을 골라 주세요.`}
        </Banner>
      );
    case 'not_image':
      return (
        <Banner tone="error" title="사진 파일만 올릴 수 있어요" icon="notImage">
          {`‘${p.name}’는 사진이 아니에요. JPG나 PNG 사진을 골라 주세요.`}
        </Banner>
      );
    case 'denied':
      return (
        <Banner tone="error" title="카메라를 쓸 수 없어요">
          설정에서 카메라 권한을 켜 주세요. 갤러리에서 사진을 고를 수도 있어요.
        </Banner>
      );
    case 'server':
      return (
        <Banner
          tone="error"
          title={p.code === 'file_too_large' ? '사진이 너무 커요' : '이 사진은 올릴 수 없어요'}
          icon={p.code === 'unsupported_type' ? 'notImage' : 'error'}
        >
          {p.message}
        </Banner>
      );
  }
}

const TIPS = [
  ['사진 한 장에 ', '문제 하나', '만 담아 주세요'],
  ['밝은 곳에서, 그림자 없이 찍어 주세요'],
  ['글자가 흐리지 않게 가까이 맞춰 주세요'],
];

function Tips() {
  const c = useColors();
  return (
    <Card>
      <H2 nativeID="tips-h">잘 읽히는 사진 찍는 법</H2>
      <View role="list" aria-labelledby="tips-h" style={{ gap: 12 }}>
        {TIPS.map(([a, b, d], i) => (
          <View role="listitem" key={i} style={{ flexDirection: 'row', gap: 12 }}>
            <View style={{ marginTop: 2 }}>
              <Icon name="check" size={22} color={c.primaryText} strokeWidth={2.4} />
            </View>
            <T style={{ flex: 1 }}>
              {a}
              {b && <T style={{ fontFamily: font.bold }}>{b}</T>}
              {d}
            </T>
          </View>
        ))}
      </View>
    </Card>
  );
}

export default function Home() {
  const c = useColors();
  const wide = useWide();
  const online = useOnline();
  const params = useLocalSearchParams<{ err?: string; msg?: string }>();
  const [problem, setProblem] = useState<Problem | null>(null);
  const [recent, setRecent] = useState<Reading[]>([]);

  useFocusEffect(
    useCallback(() => {
      listHistory().then(setRecent);
      warmup(); // restarts the worker's 90 s idle timer
      if (params.err && params.msg) setProblem({ kind: 'server', code: params.err, message: params.msg });
    }, [params.err, params.msg]),
  );

  const take = (r: PickResult) => {
    if (!r) return;
    if ('problem' in r) return setProblem(r.problem);
    setProblem(null);
    router.setParams({ err: undefined, msg: undefined });
    session.picked = r.picked;
    router.push('/crop');
  };
  const pick = async (src: 'camera' | 'library') => take(await pickPhoto(src));

  const showCaption = !!problem || wide;
  const buttons = (
    <View style={{ gap: 12 }}>
      <Button kind="large" icon="camera" label={wide ? '카메라로 찍기' : '사진 찍기'} onPress={() => pick('camera')} />
      <Button
        kind="secondary"
        icon="gallery"
        label={problem ? '다른 사진 선택' : wide ? '파일 선택' : '갤러리에서 선택'}
        onPress={() => pick('library')}
      />
      {showCaption && (
        <T v="caption" muted style={{ textAlign: 'center' }}>
          {wide ? 'JPG 또는 PNG · 5 MB 이하 · 사진 한 장에 문제 하나' : 'JPG 또는 PNG · 5 MB 이하'}
        </T>
      )}
      {!online && (
        <T v="caption" muted style={{ textAlign: 'center' }}>
          사진은 미리 찍어 둘 수 있어요. 연결되면 읽기 시작해요.
        </T>
      )}
    </View>
  );

  const recentList = recent.length > 0 && (
    <View style={{ gap: 4 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        <H2>최근에 들은 문제</H2>
        <Button kind="tertiary" label="모두 보기" href="/history" />
      </View>
      <View style={{ gap: 8 }}>
        {recent.slice(0, wide ? 3 : 1).map((r) => (
          <HistoryRow key={r.id} r={r} />
        ))}
      </View>
    </View>
  );

  const banners = (
    <>
      {!online && (
        <Banner tone="neutral" title="인터넷에 연결되어 있지 않아요">
          <T v="banner">연결되면 문제를 읽을 수 있어요. 저장한 기록은 지금도 볼 수 있어요.</T>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 4 }}>
            <Button kind="tertiary" label="연결 다시 확인" onPress={warmup} />
            <Button kind="tertiary" label="기록 보기" href="/history" />
          </View>
        </Banner>
      )}
      {problem && <ProblemBanner p={problem} />}
    </>
  );

  const pdfHint = problem?.kind === 'not_image' && (
    <Card>
      <H2>PDF나 문서에 있는 문제라면</H2>
      <T>문제가 보이도록 화면을 캡처한 뒤, 캡처한 사진을 골라 주세요.</T>
    </Card>
  );

  const title = (
    <View style={{ gap: 8 }}>
      <T v={wide ? 'displayWide' : 'display'} role="heading" aria-level={1}>
        {wide ? '수학 문제를 소리로 들어 보세요' : '수학 문제를\n소리로 들어 보세요'}
      </T>
      <T muted>문제 사진을 올리면 수식까지 한국어로 읽어 드려요.</T>
    </View>
  );

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <Header
        brand
        right={
          <View style={{ flexDirection: 'row' }}>
            {wide && <HeaderLink icon="plus" label="새 문제" href="/" />}
            <HeaderLink icon="clock" label="기록" href="/history" />
          </View>
        }
      />
      {wide ? (
        <Page>
          {banners}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 32, alignItems: 'flex-start' }}>
            <View style={{ flexGrow: 999, flexShrink: 1, flexBasis: 560, gap: 24 }}>
              {title}
              {Platform.OS === 'web' ? (
                <DropZone onFile={async (f) => take(await fromFile(f))}>
                  <View style={{ alignItems: 'center', gap: 16, padding: 40 }}>
                    <Icon name="upload" size={40} color={c.primaryText} />
                    <T v="heading" style={{ textAlign: 'center' }}>
                      문제 사진을 여기에 끌어다 놓으세요
                    </T>
                    <T muted>또는</T>
                    <View style={{ width: '100%', maxWidth: 360 }}>{buttons}</View>
                  </View>
                </DropZone>
              ) : (
                buttons
              )}
              {pdfHint}
            </View>
            <View style={{ flexGrow: 1, flexShrink: 1, flexBasis: 320, gap: 24 }}>
              <Tips />
              {recentList}
            </View>
          </View>
        </Page>
      ) : (
        <Page>
          {banners}
          {title}
          {buttons}
          {pdfHint || <Tips />}
          <View style={{ marginTop: 'auto' }}>{recentList}</View>
        </Page>
      )}
    </View>
  );
}
