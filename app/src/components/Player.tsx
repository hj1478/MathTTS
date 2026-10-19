// Audio player card (Components.dc.html §2) and the "읽어 주는 문장" highlight.
import type { AudioPlayer, AudioStatus } from 'expo-audio';
import { forwardRef, useMemo } from 'react';
import { Pressable, Text, View } from 'react-native';

import { mmss, phrases } from '@/lib/format';
import { font, useColors } from '@/lib/theme';
import { Icon, type IconName } from './Icon';
import { SeekBar } from './SeekBar';
import { H2 } from './ui';

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
    speed: number;
    onSpeed: (v: number) => void;
  }
>(function Player({ player, status, speed, onSpeed }, playRef) {
  const c = useColors();
  const dur = status.duration || 0;
  const t = status.currentTime || 0;
  const playing = status.playing;
  const toggle = () => {
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
          {mmss(t)} / {mmss(dur)}
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
            player.seekTo(0);
            player.play();
          }}
        />
      </View>
      <View role="group" aria-labelledby="speed-l" style={{ gap: 8 }}>
        <Text nativeID="speed-l" style={{ fontFamily: font.semibold, fontSize: 15, lineHeight: 22, color: c.text2 }}>
          읽는 속도
        </Text>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          {SPEEDS.map((v) => {
            const on = v === speed;
            return (
              <Pressable
                key={v}
                role="button"
                aria-pressed={on}
                accessibilityState={{ selected: on }}
                accessibilityLabel={v + '배속'}
                onPress={() => onSpeed(v)}
                style={(s) => ({
                  flex: 1,
                  minHeight: 52,
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
                  {v}x
                </Text>
              </Pressable>
            );
          })}
        </View>
      </View>
    </View>
  );
});

/**
 * The spoken sentence with the phrase being read marked. Visual only: no live
 * region, so it never talks over a screen reader (Tokens.dc.html §5).
 */
export function Spoken({ text, time, duration, big }: { text: string; time?: number; duration?: number; big?: boolean }) {
  const c = useColors();
  // speak.js passes markdown through (headings, bold); it isn't read aloud, so don't show it.
  const clean = useMemo(() => text.replace(/^#+\s*/gm, '').replace(/\*\*/g, ''), [text]);
  const segs = useMemo(() => phrases(clean, duration || 0), [clean, duration]);
  let cur = -1;
  if (duration && time != null && time > 0) segs.forEach((s, i) => time >= s.start && (cur = i));
  return (
    <Text
      style={{
        fontFamily: font.medium,
        fontSize: big ? 22 : 20,
        lineHeight: big ? 42 : 38,
        color: c.text,
      }}
    >
      {segs.map((s, i) => (
        <Text key={i}>
          {i > 0 ? ' ' : ''}
          <Text
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
      ))}
    </Text>
  );
}
