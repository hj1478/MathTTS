// Four-step progress list (Components.dc.html §3). State is shape + text, never colour alone.
import { Text, View } from 'react-native';

import { font, useColors } from '@/lib/theme';
import { Icon } from './Icon';

export type StepState = 'done' | 'current' | 'waiting' | 'failed' | 'notRun';

const LABEL: Record<StepState, string> = {
  done: '완료',
  current: '진행 중',
  waiting: '대기',
  failed: '실패',
  notRun: '진행 안 됨',
};

export const STEP_NAMES = ['업로드', '문제 읽기', '수식 해석', '음성 만들기'];

export function Steps({ states }: { states: StepState[] }) {
  const c = useColors();
  return (
    <View role="list" aria-label="진행 단계">
      {states.map((st, i) => {
        const last = i === states.length - 1;
        const circle =
          st === 'done'
            ? { backgroundColor: c.primary, borderColor: c.primary }
            : st === 'current'
              ? { backgroundColor: c.surface, borderColor: c.primary }
              : st === 'failed'
                ? { backgroundColor: c.errorBg, borderColor: c.errorText }
                : { backgroundColor: c.surface2, borderColor: c.border };
        const labelColor =
          st === 'current' ? c.primaryText : st === 'failed' ? c.errorText : st === 'done' ? c.text : c.text2;
        return (
          <View
            key={i}
            role="listitem"
            aria-current={st === 'current' || st === 'failed' ? 'step' : undefined}
            accessibilityLabel={`${i + 1}단계, ${STEP_NAMES[i]}, ${LABEL[st]}`}
            style={{ flexDirection: 'row', gap: 14, minHeight: 60 }}
          >
            <View style={{ alignItems: 'center', width: 32 }} aria-hidden>
              <View
                style={[
                  { width: 32, height: 32, borderRadius: 16, borderWidth: 2, alignItems: 'center', justifyContent: 'center' },
                  circle,
                ]}
              >
                {st === 'done' ? (
                  <Icon name="check" size={18} color={c.onPrimary} strokeWidth={3} />
                ) : st === 'current' ? (
                  <View style={{ width: 12, height: 12, borderRadius: 6, backgroundColor: c.primary }} />
                ) : (
                  <Text style={{ fontFamily: font.bold, fontSize: 15, color: st === 'failed' ? c.errorText : c.text2 }}>
                    {st === 'failed' ? '!' : i + 1}
                  </Text>
                )}
              </View>
              {!last && (
                <View
                  style={{ flex: 1, width: 2, minHeight: 16, backgroundColor: st === 'done' ? c.primary : c.border }}
                />
              )}
            </View>
            <View style={{ flex: 1, flexDirection: 'row', justifyContent: 'space-between', gap: 8, paddingTop: 3 }}>
              <Text style={{ fontFamily: font.semibold, fontSize: 17, lineHeight: 26, color: st === 'waiting' || st === 'notRun' ? c.text2 : c.text }}>
                {STEP_NAMES[i]}
              </Text>
              <Text style={{ fontFamily: font.semibold, fontSize: 15, lineHeight: 26, color: labelColor }}>{LABEL[st]}</Text>
            </View>
          </View>
        );
      })}
    </View>
  );
}
