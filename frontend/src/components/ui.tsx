import type { ReactNode } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Fonts, MaxContentWidth, useTheme } from '@/constants/theme';

export function Screen({ children }: { children: ReactNode }) {
  const t = useTheme();
  return (
    <SafeAreaView style={[styles.fill, { backgroundColor: t.background }]}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <View style={styles.column}>{children}</View>
      </ScrollView>
    </SafeAreaView>
  );
}

export function Card({ children, tone }: { children: ReactNode; tone?: 'danger' }) {
  const t = useTheme();
  return (
    <View
      style={[
        styles.card,
        tone === 'danger'
          ? { backgroundColor: t.dangerSoft, borderColor: t.dangerSoft }
          : { backgroundColor: t.card, borderColor: t.border },
      ]}>
      {children}
    </View>
  );
}

export function Label({ children }: { children: ReactNode }) {
  const t = useTheme();
  return <Text style={[styles.label, { color: t.textSecondary }]}>{children}</Text>;
}

export function Body({ children, mono, muted }: { children: ReactNode; mono?: boolean; muted?: boolean }) {
  const t = useTheme();
  return (
    <Text
      selectable
      style={[
        styles.body,
        { color: muted ? t.textSecondary : t.text },
        mono ? { fontFamily: Fonts.mono, fontSize: 14 } : { fontFamily: Fonts.sans },
      ]}>
      {children}
    </Text>
  );
}

export function Button({
  title,
  onPress,
  variant = 'primary',
  busy,
  disabled,
}: {
  title: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary';
  busy?: boolean;
  disabled?: boolean;
}) {
  const t = useTheme();
  const primary = variant === 'primary';
  const fg = primary ? t.accentText : t.accent;
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      disabled={disabled || busy}
      style={({ pressed }) => [
        styles.button,
        primary
          ? { backgroundColor: t.accent }
          : { backgroundColor: 'transparent', borderColor: t.accent, borderWidth: 1.5 },
        (pressed || disabled) && { opacity: 0.6 },
      ]}>
      {busy ? <ActivityIndicator color={fg} /> : <Text style={[styles.buttonText, { color: fg }]}>{title}</Text>}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  scroll: { flexGrow: 1, paddingHorizontal: 16, paddingVertical: 24 },
  column: { width: '100%', maxWidth: MaxContentWidth, alignSelf: 'center', gap: 16 },
  card: { borderRadius: 14, borderWidth: 1, padding: 16, gap: 10 },
  label: { fontSize: 13, fontWeight: '600', letterSpacing: 0.2, fontFamily: Fonts.sans },
  body: { fontSize: 16, lineHeight: 25 },
  button: {
    minHeight: 52,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 20,
  },
  buttonText: { fontSize: 17, fontWeight: '600', fontFamily: Fonts.sans },
});
