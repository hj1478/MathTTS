// One saved reading (Components.dc.html §5): the whole row is a link, delete is separate.
import { router } from 'expo-router';
import { Image, Pressable, Text, View } from 'react-native';

import { plainPreview, when, whenSpoken } from '@/lib/format';
import type { Reading } from '@/lib/store';
import { font, useColors } from '@/lib/theme';
import { Icon } from './Icon';

export function HistoryRow({ r, onDelete }: { r: Reading; onDelete?: () => void }) {
  const c = useColors();
  const text = plainPreview(r.normalizedText || r.ocrText) || '읽은 문제';
  return (
    <View
      style={{
        flexDirection: 'row',
        alignItems: 'center',
        borderRadius: 14,
        borderWidth: 1,
        borderColor: c.border,
        backgroundColor: c.surface,
      }}
    >
      <Pressable
        role="link"
        accessibilityLabel={`${text} ${whenSpoken(r.createdAt)}, 결과 열기`}
        onPress={() => router.push({ pathname: '/result/[id]', params: { id: r.id } })}
        style={(s) => ({
          flex: 1,
          flexDirection: 'row',
          alignItems: 'center',
          gap: 14,
          minHeight: 84,
          padding: 12,
          borderRadius: 14,
          backgroundColor: s.pressed ? c.surface2 : undefined,
          ...((s as { focused?: boolean }).focused
            ? { outlineColor: c.focus, outlineWidth: 3, outlineStyle: 'solid', outlineOffset: 3 }
            : {}),
        })}
      >
        <Image
          source={{ uri: r.imageUri }}
          style={{ width: 60, height: 60, borderRadius: 8, backgroundColor: c.surface2 }}
          resizeMode="cover"
          aria-hidden
        />
        <View style={{ flex: 1, gap: 2 }}>
          <Text numberOfLines={2} style={{ fontFamily: font.medium, fontSize: 17, lineHeight: 24, color: c.text }}>
            {text}
          </Text>
          <Text style={{ fontFamily: font.regular, fontSize: 15, lineHeight: 22, color: c.text2 }}>
            {when(r.createdAt)}
          </Text>
        </View>
        {!onDelete && <Icon name="chevron" size={20} color={c.text2} />}
      </Pressable>
      {onDelete && (
        <Pressable
          role="button"
          accessibilityLabel={`${when(r.createdAt)} 기록 삭제`}
          onPress={onDelete}
          style={(s) => ({
            width: 48,
            height: 48,
            marginRight: 8,
            borderRadius: 12,
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: s.pressed ? c.errorBg : undefined,
          })}
        >
          <Icon name="trash" size={22} color={c.errorText} />
        </Pressable>
      )}
    </View>
  );
}
