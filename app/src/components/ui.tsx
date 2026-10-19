// Text, buttons, banners and the screen frame (design/ui/Components.dc.html).
import { Link, router, type Href } from 'expo-router';
import type { ReactNode } from 'react';
import {
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  type PressableProps,
  type StyleProp,
  type TextProps,
  type TextStyle,
  type ViewStyle,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { font, useColors, useWide, type Colors } from '@/lib/theme';
import { Icon, type IconName } from './Icon';

// ---- Text ----------------------------------------------------------------

const type = {
  display: { fontSize: 28, lineHeight: 38, fontFamily: font.bold, letterSpacing: -0.5 },
  displayWide: { fontSize: 36, lineHeight: 46, fontFamily: font.bold, letterSpacing: -0.7 },
  title: { fontSize: 26, lineHeight: 34, fontFamily: font.bold, letterSpacing: -0.4 },
  heading: { fontSize: 19, lineHeight: 26, fontFamily: font.bold },
  section: { fontSize: 17, lineHeight: 24, fontFamily: font.bold },
  spoken: { fontSize: 20, lineHeight: 38, fontFamily: font.medium },
  body: { fontSize: 17, lineHeight: 26, fontFamily: font.regular },
  banner: { fontSize: 16, lineHeight: 24, fontFamily: font.regular },
  caption: { fontSize: 15, lineHeight: 22, fontFamily: font.regular },
} satisfies Record<string, TextStyle>;

export function T({
  v = 'body',
  muted,
  style,
  ...rest
}: TextProps & { v?: keyof typeof type; muted?: boolean }) {
  const c = useColors();
  return <Text {...rest} style={[type[v], { color: muted ? c.text2 : c.text }, style]} />;
}

export const H1 = (p: TextProps & { v?: keyof typeof type }) => (
  <T v="title" role="heading" aria-level={1} {...p} />
);
export const H2 = (p: TextProps & { v?: keyof typeof type }) => (
  <T v="section" role="heading" aria-level={2} {...p} />
);

// ---- Buttons ---------------------------------------------------------------

type Kind = 'primary' | 'large' | 'secondary' | 'tertiary' | 'danger' | 'waiting';

function focusRing(c: Colors, focused: boolean): ViewStyle {
  return Platform.OS === 'web' && focused
    ? ({ outlineColor: c.focus, outlineWidth: 3, outlineStyle: 'solid', outlineOffset: 3 } as ViewStyle)
    : {};
}

export function Button({
  kind = 'primary',
  icon,
  label,
  onPress,
  href,
  style,
  ...rest
}: {
  kind?: Kind;
  icon?: IconName;
  label: string;
  onPress?: () => void;
  href?: Href;
  style?: StyleProp<ViewStyle>;
} & Omit<PressableProps, 'style' | 'children' | 'onPress'>) {
  const c = useColors();
  const box: Record<Kind, ViewStyle> = {
    primary: { minHeight: 56, borderRadius: 14, backgroundColor: c.primary, paddingHorizontal: 20 },
    large: { minHeight: 64, borderRadius: 16, backgroundColor: c.primary, paddingHorizontal: 20 },
    secondary: {
      minHeight: 56,
      borderRadius: 14,
      backgroundColor: c.surface,
      borderWidth: 2,
      borderColor: c.borderStrong,
      paddingHorizontal: 20,
    },
    tertiary: { minHeight: 48, minWidth: 48, paddingHorizontal: 8 },
    danger: { minHeight: 48, minWidth: 48, paddingHorizontal: 8 },
    waiting: {
      minHeight: 56,
      borderRadius: 14,
      backgroundColor: c.surface2,
      borderWidth: 2,
      borderStyle: 'dashed',
      borderColor: c.borderStrong,
      paddingHorizontal: 20,
    },
  };
  const fg: Record<Kind, string> = {
    primary: c.onPrimary,
    large: c.onPrimary,
    secondary: c.text,
    tertiary: c.primaryText,
    danger: c.errorText,
    waiting: c.text2,
  };
  const text: TextStyle =
    kind === 'large'
      ? { fontSize: 19, lineHeight: 26, fontFamily: font.bold }
      : kind === 'primary'
        ? { fontSize: 17, lineHeight: 24, fontFamily: font.bold }
        : kind === 'tertiary' || kind === 'danger'
          ? { fontSize: 16, lineHeight: 24, fontFamily: font.semibold }
          : { fontSize: 17, lineHeight: 24, fontFamily: font.semibold };
  const waiting = kind === 'waiting';
  const press = waiting ? undefined : href ? () => router.push(href) : onPress;
  return (
    <Pressable
      role={href ? 'link' : 'button'}
      aria-disabled={waiting || undefined}
      accessibilityState={waiting ? { disabled: true } : undefined}
      accessibilityLabel={label}
      onPress={press}
      {...rest}
      style={(s) => [
        styles.btn,
        box[kind],
        s.pressed && !waiting && { opacity: 0.85 },
        focusRing(c, !!(s as { focused?: boolean }).focused),
        style,
      ]}
    >
      {icon && <Icon name={icon} size={kind === 'large' ? 26 : 22} color={fg[kind]} />}
      <Text style={[text, { color: fg[kind], textAlign: 'center', flexShrink: 1 }]}>{label}</Text>
    </Pressable>
  );
}

export function IconButton({
  icon,
  label,
  onPress,
}: {
  icon: IconName;
  label: string;
  onPress: () => void;
}) {
  const c = useColors();
  return (
    <Pressable
      role="button"
      accessibilityLabel={label}
      onPress={onPress}
      style={(s) => [
        styles.iconBtn,
        s.pressed && { backgroundColor: c.surface2 },
        focusRing(c, !!(s as { focused?: boolean }).focused),
      ]}
    >
      <Icon name={icon} size={24} color={c.text} />
    </Pressable>
  );
}

// ---- Banners ---------------------------------------------------------------

type Tone = 'info' | 'note' | 'error' | 'neutral';

export function Banner({
  tone,
  title,
  children,
  action,
  icon,
}: {
  tone: Tone;
  title?: string;
  children?: ReactNode;
  action?: ReactNode;
  icon?: IconName;
}) {
  const c = useColors();
  const pal = {
    info: [c.infoBg, c.infoText, c.infoBorder],
    note: [c.noteBg, c.noteText, c.noteBorder],
    error: [c.errorBg, c.errorText, c.errorBorder],
    neutral: [c.surface2, c.text, c.border],
  }[tone];
  const small = tone === 'note';
  const ic: IconName = icon ?? (tone === 'error' ? 'error' : tone === 'neutral' ? 'offline' : 'info');
  return (
    <View
      role={tone === 'error' || tone === 'neutral' ? 'alert' : 'status'}
      accessibilityLiveRegion={tone === 'error' || tone === 'neutral' ? 'assertive' : 'polite'}
      style={{
        flexDirection: 'row',
        gap: 12,
        padding: small ? 12 : 16,
        paddingHorizontal: small ? 14 : 16,
        borderRadius: 14,
        borderWidth: 1,
        backgroundColor: pal[0],
        borderColor: pal[2],
      }}
    >
      <Icon name={ic} size={small ? 20 : 24} color={pal[1]} />
      <View style={{ flex: 1, gap: 4 }}>
        {title && <Text style={[type.section, { color: pal[1] }]}>{title}</Text>}
        {typeof children === 'string' ? (
          <Text style={[small ? type.caption : type.banner, { color: pal[1] }]}>{children}</Text>
        ) : (
          children
        )}
        {action}
      </View>
    </View>
  );
}

export const PROTOTYPE_NOTE = '연구용 시제품입니다. 사진과 읽은 내용이 같은지 확인해 주세요.';

// ---- Frame -----------------------------------------------------------------

export function Header({
  title,
  back,
  right,
  brand,
}: {
  title?: string;
  back?: { label: string; onPress?: () => void };
  right?: ReactNode;
  brand?: boolean;
}) {
  const c = useColors();
  const wide = useWide();
  const insets = useSafeAreaInsets();
  return (
    <View
      style={{
        paddingTop: insets.top,
        backgroundColor: c.surface,
        borderBottomWidth: 1,
        borderBottomColor: c.border,
      }}
    >
      <View
        style={[
          styles.header,
          { paddingLeft: back ? 4 : 20 },
          wide && { maxWidth: 1168, width: '100%', alignSelf: 'center', paddingHorizontal: 24 },
        ]}
      >
        {back && (
          <IconButton
            icon="back"
            label={back.label}
            onPress={back.onPress ?? (() => (router.canGoBack() ? router.back() : router.replace('/')))}
          />
        )}
        {brand ? (
          <Link href="/" accessibilityLabel="MathTTS 처음 화면">
            <T v="heading">MathTTS</T>
          </Link>
        ) : (
          title && (
            <T v="heading" role="heading" aria-level={1} style={{ flex: 1 }} numberOfLines={1}>
              {title}
            </T>
          )
        )}
        <View style={{ flex: 1 }} />
        {right}
      </View>
    </View>
  );
}

export function HeaderLink({ icon, label, href }: { icon: IconName; label: string; href: Href }) {
  const c = useColors();
  return (
    <Pressable
      role="link"
      onPress={() => router.push(href)}
      style={(s) => [
        styles.headerLink,
        s.pressed && { backgroundColor: c.surface2 },
        focusRing(c, !!(s as { focused?: boolean }).focused),
      ]}
    >
      <Icon name={icon} size={22} color={c.text} />
      <T style={{ fontFamily: font.semibold }}>{label}</T>
    </Pressable>
  );
}

/** Scrolling page body: 20 px gutters, 1120 px max width on desktop. */
export function Page({
  children,
  footer,
  contentStyle,
}: {
  children: ReactNode;
  footer?: ReactNode;
  contentStyle?: StyleProp<ViewStyle>;
}) {
  const c = useColors();
  const wide = useWide();
  const insets = useSafeAreaInsets();
  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={[
          {
            flexGrow: 1,
            gap: 24,
            paddingHorizontal: wide ? 24 : 20,
            paddingTop: wide ? 40 : 28,
            paddingBottom: footer ? 24 : 24 + insets.bottom,
            width: '100%',
            maxWidth: wide ? 1168 : 640,
            alignSelf: 'center',
          },
          contentStyle,
        ]}
      >
        {children}
      </ScrollView>
      {footer && (
        <View
          style={{
            backgroundColor: c.surface,
            borderTopWidth: 1,
            borderTopColor: c.border,
            paddingBottom: insets.bottom,
          }}
        >
          <View
            style={{
              flexDirection: 'row',
              flexWrap: 'wrap',
              gap: 12,
              padding: 16,
              paddingHorizontal: 20,
              width: '100%',
              maxWidth: 640,
              alignSelf: 'center',
            }}
          >
            {footer}
          </View>
        </View>
      )}
    </View>
  );
}

export function Card({ children, style }: { children: ReactNode; style?: StyleProp<ViewStyle> }) {
  const c = useColors();
  return (
    <View
      style={[
        { padding: 20, gap: 14, borderRadius: 16, backgroundColor: c.surface, borderWidth: 1, borderColor: c.border },
        style,
      ]}
    >
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  btn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10 },
  iconBtn: { width: 48, height: 48, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  header: { flexDirection: 'row', alignItems: 'center', gap: 8, minHeight: 64, paddingRight: 8 },
  headerLink: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    minHeight: 48,
    paddingHorizontal: 14,
    borderRadius: 12,
  },
});
