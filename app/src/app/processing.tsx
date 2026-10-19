// 3 처리 중 (Processing.dc.html) and what can end it short of a result:
// 3b ProcessingFailed, E2 RateLimited, E5 NothingRecognized, and a dropped connection.
import { router } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { AccessibilityInfo, Image, Platform, View } from 'react-native';

import { Icon } from '@/components/Icon';
import { MathText } from '@/components/MathText';
import { Steps, type StepState } from '@/components/Steps';
import { Banner, Button, Card, H1, H2, Header, Page, T } from '@/components/ui';
import { ApiError, getJob, submitJob, type Job, type StageState } from '@/lib/api';
import { elapsed } from '@/lib/format';
import { pickPhoto } from '@/lib/image';
import { readingFromJob, session } from '@/lib/store';
import { font, useColors } from '@/lib/theme';

const POLL_MS = 500; // docs/API.md: every 0.5 s from the start of the previous poll
const GIVE_UP_S = 600; // "10분이 지나도 끝나지 않으면 알려 드릴게요"
const SLOW_OCR_S = 12; // a warm worker finishes OCR in ~4 s; longer means a cold start

type Phase =
  | { k: 'submitting' }
  | { k: 'polling'; id: string }
  | { k: 'failed'; title: string; message: string; job?: Job }
  | { k: 'timeout'; job?: Job }
  | { k: 'rate_limited'; until: number }
  | { k: 'nothing' };

const STEP_TITLE = ['사진을 올리고 있어요', '문제를 읽고 있어요', '수식을 해석하고 있어요', '음성을 만들고 있어요'];

function stepStates(job: Job | undefined, uploaded: boolean, failedRun = false): StepState[] {
  const m = (s: StageState): StepState =>
    s === 'running' ? 'current' : s === 'done' ? 'done' : s === 'failed' ? 'failed' : s === 'skipped' ? 'notRun' : 'waiting';
  if (!uploaded) return ['current', 'waiting', 'waiting', 'waiting'];
  if (!job) return failedRun ? ['done', 'failed', 'notRun', 'notRun'] : ['done', 'current', 'waiting', 'waiting'];
  const s = job.stage_status;
  const ocr = job.status === 'queued' ? 'current' : m(s.ocr);
  let mid: StepState;
  if (s.normalize === 'failed' || s.speech === 'failed') mid = 'failed';
  else if (s.speech === 'done') mid = 'done';
  else if (s.normalize === 'running' || s.speech === 'running' || s.normalize === 'done') mid = 'current';
  else mid = m(s.normalize);
  const states: StepState[] = ['done', ocr, mid, m(s.tts)];
  if (failedRun) {
    // The 10-minute cutoff: the step that was running failed, later ones never ran.
    const i = states.findIndex((x) => x === 'current' || x === 'waiting');
    if (i > 0) return states.map((x, j) => (j < i ? x : j === i ? 'failed' : 'notRun'));
  }
  return states;
}

export default function Processing() {
  const c = useColors();
  const upload = session.upload;
  const [phase, setPhase] = useState<Phase>({ k: 'submitting' });
  const [job, setJob] = useState<Job>();
  const [attempt, setAttempt] = useState(0);
  const [start, setStart] = useState(Date.now());
  const [now, setNow] = useState(Date.now());
  const [netDown, setNetDown] = useState(false);
  const alive = useRef(true);

  useEffect(() => {
    if (!upload) router.replace('/');
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      alive.current = false;
      clearInterval(t);
    };
  }, [upload]);

  // Submit, then poll until the job ends.
  useEffect(() => {
    if (!upload) return;
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    const t0 = Date.now();

    (async () => {
      let id: string;
      try {
        id = await submitJob(upload);
      } catch (e) {
        if (stop) return;
        const err = e instanceof ApiError ? e : new ApiError(0, 'network', String(e));
        if (err.status === 429) return setPhase({ k: 'rate_limited', until: Date.now() + (err.retryAfter ?? 60) * 1000 });
        if (err.status === 0) {
          setNetDown(true);
          return setPhase({ k: 'failed', title: '연결이 끊겼어요', message: '사진은 그대로 있어요. 연결을 확인하고 다시 시도해 주세요.' });
        }
        if (err.status >= 400 && err.status < 500)
          return router.replace({ pathname: '/', params: { err: err.code, msg: err.message } });
        return setPhase({ k: 'failed', title: '서버에서 오류가 났어요', message: err.message });
      }
      if (stop) return;
      setPhase({ k: 'polling', id });

      let lastOk = Date.now();
      const poll = async () => {
        const began = Date.now();
        if ((began - t0) / 1000 > GIVE_UP_S) return setPhase({ k: 'timeout' });
        try {
          const j = await getJob(id);
          if (stop) return;
          lastOk = Date.now();
          setNetDown(false);
          setJob(j);
          if (j.status === 'done') {
            const r = readingFromJob(j, upload);
            session.readings.set(r.id, r);
            return router.replace({ pathname: '/result/[id]', params: { id: r.id } });
          }
          if (j.status === 'failed') {
            if (j.error?.code === 'no_text_found') return setPhase({ k: 'nothing' });
            return setPhase({
              k: 'failed',
              title: j.error?.code === 'timeout' ? '시간이 너무 오래 걸렸어요' : '처리 중 문제가 생겼어요',
              message: j.error?.message ?? '같은 사진으로 다시 시도해 주세요.',
              job: j,
            });
          }
        } catch (e) {
          if (stop) return;
          if (e instanceof ApiError && e.status === 404)
            return setPhase({ k: 'failed', title: '작업을 찾을 수 없어요', message: e.message });
          // Transient: keep polling, say so after 15 s without an answer.
          if (Date.now() - lastOk > 15000) setNetDown(true);
        }
        timer = setTimeout(poll, Math.max(0, POLL_MS - (Date.now() - began)));
      };
      poll();
    })();

    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [upload, attempt]);

  const uploaded = phase.k !== 'submitting';
  const states = stepStates(job, uploaded, phase.k === 'timeout' || (phase.k === 'failed' && !job));
  const curIdx = Math.max(0, states.findIndex((s) => s === 'current'));
  const secs = (now - start) / 1000;

  // Announce a step change once (Tokens.dc.html §5); the web heading is an aria-live region.
  const lastAnnounced = useRef(-1);
  useEffect(() => {
    if (phase.k !== 'polling' && phase.k !== 'submitting') return;
    if (curIdx === lastAnnounced.current) return;
    lastAnnounced.current = curIdx;
    if (Platform.OS !== 'web')
      AccessibilityInfo.announceForAccessibility(`${curIdx + 1}단계, ${STEP_NAMES_SHORT[curIdx]}, 진행 중`);
  }, [curIdx, phase.k]);

  const retry = () => {
    setStart(Date.now());
    setJob(undefined);
    setNetDown(false);
    setPhase({ k: 'submitting' });
    setAttempt((a) => a + 1);
  };
  const repick = async (src: 'camera' | 'library') => {
    const r = await pickPhoto(src);
    if (!r) return;
    if ('problem' in r) return router.replace('/');
    session.picked = r.picked;
    router.replace('/crop');
  };

  if (!upload) return null;

  // ---- E2 요청 제한 ----
  if (phase.k === 'rate_limited') {
    const left = Math.max(0, Math.ceil((phase.until - now) / 1000));
    const label = left >= 60 ? `${Math.floor(left / 60)}분 ${String(left % 60).padStart(2, '0')}초` : `${left}초`;
    return (
      <Shell title="문제 읽기">
        <H1>잠시 후 다시 시도해 주세요</H1>
        <Banner tone="info" title="요청이 많아 잠시 기다려야 해요">
          짧은 시간에 요청이 많았어요. 사진은 그대로 있으니 시간이 지나면 다시 시도할 수 있어요.
        </Banner>
        <Card style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
          <T muted>다시 시도할 수 있을 때까지</T>
          <T v="heading" style={{ fontVariant: ['tabular-nums'] }} accessibilityLabel={left ? `${label} 남음` : '지금 다시 시도할 수 있어요'}>
            {left ? label : '지금'}
          </T>
        </Card>
        <Photo uri={upload.uri} caption="선택한 사진" />
        <View style={{ gap: 12, marginTop: 'auto' }}>
          {left > 0 ? (
            <Button kind="waiting" label={`${label} 후 다시 시도`} />
          ) : (
            <Button kind="primary" icon="restart" label="다시 시도" onPress={retry} />
          )}
          <Button kind="tertiary" label="처음으로" onPress={() => router.replace('/')} />
        </View>
      </Shell>
    );
  }

  // ---- E5 인식된 문제 없음 ----
  if (phase.k === 'nothing') {
    const tips = [
      '문제 글자가 화면을 가득 채우도록 가까이 찍어 주세요',
      '밝은 곳에서 빛 반사와 그림자를 피해 주세요',
      '휴대폰을 종이와 평행하게 들어 주세요',
    ];
    return (
      <Shell title="읽은 결과">
        <Photo uri={upload.uri} caption="올린 사진" />
        <View style={{ gap: 8 }}>
          <H1>{'사진에서 문제를\n찾지 못했어요'}</H1>
          <T muted>글자를 알아볼 수 없었어요. 아래 방법으로 다시 찍어 보세요.</T>
        </View>
        <Card>
          <H2>이렇게 해 보세요</H2>
          <View role="list" style={{ gap: 12 }}>
            {tips.map((t, i) => (
              <View role="listitem" key={i} style={{ flexDirection: 'row', gap: 12 }}>
                <View style={{ width: 28, height: 28, borderRadius: 14, backgroundColor: c.primarySoft, alignItems: 'center', justifyContent: 'center' }}>
                  <T style={{ fontFamily: font.bold, color: c.onPrimarySoft }}>{i + 1}</T>
                </View>
                <T style={{ flex: 1 }}>{t}</T>
              </View>
            ))}
          </View>
        </Card>
        <View style={{ gap: 12, marginTop: 'auto' }}>
          <Button kind="primary" icon="camera" label="다시 찍기" onPress={() => repick('camera')} />
          <Button kind="secondary" icon="gallery" label="갤러리에서 선택" onPress={() => repick('library')} />
        </View>
      </Shell>
    );
  }

  // ---- 3b 처리 실패 ----
  if (phase.k === 'failed' || phase.k === 'timeout') {
    const timeout = phase.k === 'timeout';
    return (
      <Shell title="문제 읽기">
        <H1>문제를 읽지 못했어요</H1>
        <Banner tone={netDown ? 'neutral' : 'error'} title={timeout ? '10분이 지나도 끝나지 않았어요' : phase.title}>
          {timeout
            ? '서버가 응답하지 않았어요. 사진을 다시 찍지 않아도 돼요. 같은 사진으로 다시 시도해 주세요.'
            : phase.message}
        </Banner>
        <Elapsed secs={timeout ? GIVE_UP_S : secs} />
        <Steps states={stepStates(phase.job ?? job, true, true)} />
        <View style={{ gap: 12, marginTop: 'auto' }}>
          <Button kind="primary" icon="restart" label="다시 시도" onPress={retry} />
          <Button kind="tertiary" label="다른 사진 선택" onPress={() => router.replace('/')} />
        </View>
      </Shell>
    );
  }

  // ---- 3 처리 중 ----
  const slow = job?.status === 'queued' || (uploaded && states[1] !== 'done' && secs > SLOW_OCR_S);
  const early = job?.stages?.normalized?.text ?? job?.stages?.ocr?.text;
  return (
    <Shell title="문제 읽는 중">
      <View aria-live="polite" style={{ gap: 4 }}>
        <T v="caption" muted style={{ fontFamily: font.semibold }}>
          4단계 중 {curIdx + 1}단계
        </T>
        <H1>{STEP_TITLE[curIdx]}</H1>
      </View>
      <Elapsed secs={secs} />
      {netDown && (
        <Banner tone="neutral" title="연결이 불안정해요">
          서버의 답을 기다리고 있어요. 사진은 그대로 있어요.
        </Banner>
      )}
      {slow && !netDown && (
        <Banner tone="info" title="서버를 준비하고 있어요">
          처음에는 몇 분 걸릴 수 있어요. 멈춘 것이 아니에요. 단계가 끝나면 자동으로 넘어가요.
        </Banner>
      )}
      <Steps states={states} />
      {early && (
        <Card>
          <H2>지금까지 읽은 문제</H2>
          <MathText text={early} label={job?.stages?.speech?.text} />
        </Card>
      )}
      <View style={{ gap: 8, marginTop: 'auto', alignItems: 'center' }}>
        <T v="caption" muted style={{ textAlign: 'center' }}>
          10분이 지나도 끝나지 않으면 알려 드릴게요.
        </T>
        <Button kind="tertiary" label="취소" onPress={() => router.replace('/')} />
      </View>
    </Shell>
  );
}

const STEP_NAMES_SHORT = ['업로드', '문제 읽기', '수식 해석', '음성 만들기'];

function Shell({ title, children }: { title: string; children: React.ReactNode }) {
  const c = useColors();
  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <Header title={title} />
      <Page>{children}</Page>
    </View>
  );
}

function Elapsed({ secs }: { secs: number }) {
  const c = useColors();
  return (
    <View
      style={{
        flexDirection: 'row',
        alignItems: 'center',
        gap: 10,
        padding: 14,
        paddingHorizontal: 16,
        borderRadius: 14,
        backgroundColor: c.surface,
        borderWidth: 1,
        borderColor: c.border,
      }}
    >
      <Icon name="clock" size={22} color={c.text2} />
      <T muted style={{ flex: 1 }}>
        경과 시간
      </T>
      {/* Updated every second on screen only; never announced. */}
      <T v="heading" style={{ fontVariant: ['tabular-nums'] }} accessibilityLiveRegion="none">
        {elapsed(secs)}
      </T>
    </View>
  );
}

function Photo({ uri, caption }: { uri: string; caption: string }) {
  const c = useColors();
  return (
    <View style={{ gap: 8 }}>
      <Image
        source={{ uri }}
        accessibilityLabel={caption}
        resizeMode="contain"
        style={{ width: '100%', height: 200, borderRadius: 12, backgroundColor: c.surface2 }}
      />
      <T v="caption" muted>
        {caption}
      </T>
    </View>
  );
}
