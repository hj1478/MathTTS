// Audio player card (Components.dc.html §2) and the "읽어 주는 문장" highlight.
import type { AudioPlayer, AudioStatus } from 'expo-audio';
import { forwardRef, useMemo, useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { mmss, phrases } from '@/lib/format';
import { font, useColors } from '@/lib/theme';
import { Icon, type IconName } from './Icon';
import { SeekBar } from './SeekBar';
import { Button, H2 } from './ui';

export const SPEEDS = [0.75, 1, 1.25];

export type ViewRef = React.ComponentRef<typeof View>;

function Round({
  icon,
  label,
  big,
  onPress,
  ref,
}: {
  icon: IconName;
  label: string;
  big?: boolean;
  onPress: () => void;
  ref?: React.Ref<ViewRef>;
}) {
  const c = useColors();
  const size = big ? 80 : 56;
  return (
    <Pressable
      ref={ref}
      role="button"
      accessibilityLabel={label}
      onPress={onPress}
      style={(s) => ({
        alignItems: 'center',
        gap: 6,
        minWidth: 72,
        opacity: s.pressed ? 0.85 : 1,
        ...((s as { focused?: boolean }).focused
          ? { outlineColor: c.focus, outlineWidth: 3, outlineStyle: 'solid', outlineOffset: 3, borderRadius: 16 }
          : {}),
      })}
    >
      <View
        style={{
          width: size,
          height: size,
          borderRadius: size / 2,
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: big ? c.primary : c.surface,
          borderWidth: big ? 0 : 2,
          borderColor: c.borderStrong,
        }}
      >
        <Icon name={icon} size={big ? 34 : 24} color={big ? c.onPrimary : c.text} />
      </View>
      <Text
        style={{
          fontFamily: big ? font.bold : font.semibold,
          fontSize: big ? 16 : 15,
          lineHeight: 20,
          color: c.text,
          textAlign: 'center',
        }}
      >
        {label}
      </Text>
    </Pressable>
  );
}

export const Player = forwardRef<
  ViewRef,
  {
    player: AudioPlayer;
    status: AudioStatus;
    duration: number; // seconds; the screen's own figure when the player reports none
    loading?: boolean; // the MP3 is still downloading
    onPlayWhenLoaded?: () => void; // 재생 pressed while loading
    speed: number;
    onSpeed: (v: number) => void;
  }
>(function Player({ player, status, duration, loading, onPlayWhenLoaded, speed, onSpeed }, playRef) {
  const c = useColors();
  const dur = duration || 0;
  const t = Math.min(status.currentTime || 0, dur || Infinity);
  const playing = status.playing;
  const toggle = () => {
    if (loading) return onPlayWhenLoaded?.();
    if (playing) return player.pause();
    if (dur && t >= dur - 0.05) player.seekTo(0);
    player.play();
  };
  return (
    <View
      style={{ padding: 20, gap: 14, borderRadius: 20, backgroundColor: c.surface, borderWidth: 1, borderColor: c.border }}
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Icon name="speaker" size={22} color={c.primaryText} />
          <H2 v="heading">문제 듣기</H2>
        </View>
        <Text style={{ fontFamily: font.medium, fontSize: 17, lineHeight: 24, color: c.text2, fontVariant: ['tabular-nums'] }}>
          {loading ? '불러오는 중…' : `${mmss(t)} / ${mmss(dur)}`}
        </Text>
      </View>
      <SeekBar
        value={t}
        max={dur}
        onSeek={(v) => player.seekTo(v)}
        valueText={`${Math.floor(t)}초 / ${Math.floor(dur)}초`}
      />
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-around', alignItems: 'flex-start', gap: 12 }}>
        <Round icon="rewind" label="5초 전" onPress={() => player.seekTo(Math.max(0, t - 5))} />
        <Round ref={playRef} big icon={playing ? 'pause' : 'play'} label={playing ? '일시정지' : '재생'} onPress={toggle} />
        <Round
          icon="restart"
          label="처음부터"
          onPress={() => {
            if (loading) return onPlayWhenLoaded?.();
            player.seekTo(0);
            player.play();
          }}
        />
      </View>
      <Choice
        id="speed-l"
        title="읽는 속도"
        value={speed}
        onPick={onSpeed}
        options={SPEEDS.map((v) => ({ value: v, text: v + 'x', label: v + '배속' }))}
      />
    </View>
  );
});

/** A row of buttons of which one is on (읽는 속도, 읽는 방식). */
export function Choice<V extends string | number>({
  id,
  title,
  value,
  options,
  onPick,
}: {
  id: string; // of the title, which names the group
  title: string;
  value: V;
  options: { value: V; text: string; label?: string }[];
  onPick: (v: V) => void;
}) {
  const c = useColors();
  return (
    <View role="group" aria-labelledby={id} style={{ gap: 8 }}>
      <Text nativeID={id} style={{ fontFamily: font.semibold, fontSize: 15, lineHeight: 22, color: c.text2 }}>
        {title}
      </Text>
      <View style={{ flexDirection: 'row', gap: 8 }}>
        {options.map((o) => {
          const on = o.value === value;
          return (
            <Pressable
              key={String(o.value)}
              role="button"
              aria-pressed={on}
              accessibilityState={{ selected: on }}
              accessibilityLabel={o.label ?? o.text}
              onPress={() => onPick(o.value)}
              style={(s) => ({
                flex: 1,
                minHeight: 52,
                paddingHorizontal: 8,
                borderRadius: 12,
                borderWidth: 2,
                flexDirection: 'row',
                gap: 6,
                alignItems: 'center',
                justifyContent: 'center',
                borderColor: on ? c.primary : c.borderStrong,
                backgroundColor: on ? c.primarySoft : c.surface,
                ...((s as { focused?: boolean }).focused
                  ? { outlineColor: c.focus, outlineWidth: 3, outlineStyle: 'solid', outlineOffset: 3 }
                  : {}),
              })}
            >
              {on && <Icon name="check" size={18} color={c.onPrimarySoft} strokeWidth={2.6} />}
              <Text
                style={{
                  fontFamily: on ? font.bold : font.semibold,
                  fontSize: 17,
                  color: on ? c.onPrimarySoft : c.text,
                }}
              >
                {o.text}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

// A phone shows this much of a long sentence at a time (the part being read).
const SHORT_CHARS = 70;

/**
 * The spoken sentence with the phrase being read marked. Visual only: no live
 * region, so it never talks over a screen reader (Tokens.dc.html §5).
 *
 * `compact` (a phone): a long sentence shows only the part being read, about
 * three lines, with 전체 문장 보기 to open the rest.
 *
 * `onSeek`: pressing a phrase asks to play from where it starts (seconds).
 */
export function Spoken({
  text,
  time,
  duration,
  big,
  compact,
  onSeek,
}: {
  text: string;
  time?: number;
  duration?: number;
  big?: boolean;
  compact?: boolean;
  onSeek?: (seconds: number) => void;
}) {
  const c = useColors();
  const [open, setOpen] = useState(false);
  // speak.js passes markdown through (headings, bold); it isn't read aloud, so don't show it.
  const clean = useMemo(() => text.replace(/^#+\s*/gm, '').replace(/\*\*/g, ''), [text]);
  const segs = useMemo(() => phrases(clean, duration || 0), [clean, duration]);
  // The sentence in parts of about SHORT_CHARS: [first phrase, one past the last].
  const parts = useMemo(() => {
    const out: [number, number][] = [];
    let from = 0;
    let n = 0;
    segs.forEach((s, i) => {
      n += s.text.length + 1;
      if (n >= SHORT_CHARS || i === segs.length - 1) {
        out.push([from, i + 1]);
        from = i + 1;
        n = 0;
      }
    });
    return out;
  }, [segs]);
  let cur = -1;
  if (duration && time != null && time > 0) segs.forEach((s, i) => time >= s.start && (cur = i));
  const long = !!compact && parts.length > 1;
  const short = long && !open;
  const [from, to] = short ? (parts.find(([, end]) => cur < end) ?? parts[0]!) : [0, segs.length];
  return (
    <View style={{ gap: 4 }}>
      <Text
        // a screen reader gets the whole sentence, whatever part is showing
        accessibilityLabel={short ? clean : undefined}
        style={{
          fontFamily: font.medium,
          fontSize: big ? 22 : compact ? 18 : 20,
          lineHeight: big ? 42 : compact ? 32 : 38,
          color: c.text,
        }}
      >
        {from > 0 && <Text style={{ color: c.text2 }}>… </Text>}
        {segs.slice(from, to).map((s, k) => {
          const i = from + k;
          return (
            <Text key={i}>
              {k > 0 ? ' ' : ''}
              <Text
                // a phrase's start is an estimate: begin a little early so its first word isn't cut
                onPress={onSeek && duration ? () => onSeek(Math.max(0, s.start - 0.4)) : undefined}
                style={
                  i === cur
                    ? {
                        backgroundColor: c.hlBg,
                        color: c.hlText,
                        textDecorationLine: 'underline',
                        textDecorationColor: c.hlLine,
                      }
                    : undefined
                }
              >
                {s.text}
              </Text>
            </Text>
          );
        })}
        {to < segs.length && <Text style={{ color: c.text2 }}> …</Text>}
      </Text>
      {long && (
        <View style={{ alignSelf: 'flex-start', marginLeft: -8 }}>
          <Button
            kind="tertiary"
            label={open ? '접기' : '전체 문장 보기'}
            aria-expanded={open}
            onPress={() => setOpen(!open)}
          />
        </View>
      )}
    </View>
  );
}
