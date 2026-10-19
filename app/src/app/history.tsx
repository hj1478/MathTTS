// 5 기록 (History.dc.html). Deleting shows a 되돌리기 notice instead of a dialog.
import { useFocusEffect } from 'expo-router';
import { useCallback, useRef, useState } from 'react';
import { Alert, Platform, View } from 'react-native';

import { HistoryRow } from '@/components/HistoryRow';
import { Banner, Button, H2, Header, Page, T } from '@/components/ui';
import { isToday } from '@/lib/format';
import { clearHistory, dropReadingFiles, listHistory, removeReading, saveReading, type Reading } from '@/lib/store';
import { useColors } from '@/lib/theme';

export default function History() {
  const c = useColors();
  const [items, setItems] = useState<Reading[] | null>(null);
  const [undo, setUndo] = useState<Reading | null>(null);
  const undoTimer = useRef<ReturnType<typeof setTimeout>>(undefined);

  const load = useCallback(() => {
    listHistory().then(setItems);
  }, []);
  useFocusEffect(load);

  const del = async (r: Reading) => {
    await removeReading(r.id, { keepFiles: true });
    clearTimeout(undoTimer.current);
    if (undo) dropReadingFiles(undo); // only the latest delete can be undone
    setUndo(r);
    undoTimer.current = setTimeout(() => {
      dropReadingFiles(r);
      setUndo((u) => (u?.id === r.id ? null : u));
    }, 8000);
    load();
  };

  const restore = async () => {
    if (!undo) return;
    clearTimeout(undoTimer.current);
    await saveReading(undo);
    setUndo(null);
    load();
  };

  const clearAll = () => {
    const go = async () => {
      await clearHistory();
      load();
    };
    if (Platform.OS === 'web') {
      if (window.confirm('기록을 모두 지울까요? 되돌릴 수 없어요.')) go();
    } else {
      Alert.alert('기록을 모두 지울까요?', '되돌릴 수 없어요.', [
        { text: '취소', style: 'cancel' },
        { text: '모두 지우기', style: 'destructive', onPress: go },
      ]);
    }
  };

  const today = (items ?? []).filter((r) => isToday(r.createdAt));
  const earlier = (items ?? []).filter((r) => !isToday(r.createdAt));

  const group = (title: string, list: Reading[]) =>
    list.length > 0 && (
      <View style={{ gap: 12 }}>
        <H2>{title}</H2>
        <View role="list" style={{ gap: 8 }}>
          {list.map((r) => (
            <View role="listitem" key={r.id}>
              <HistoryRow r={r} onDelete={() => del(r)} />
            </View>
          ))}
        </View>
      </View>
    );

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <Header title="기록" back={{ label: '뒤로' }} />
      <Page>
        <T muted>최근 결과는 이 기기에만 저장돼요. 계정은 필요 없어요.</T>
        {undo && (
          <Banner
            tone="neutral"
            icon="trash"
            title="기록을 지웠어요"
            action={
              <View style={{ alignSelf: 'flex-start' }}>
                <Button kind="tertiary" label="되돌리기" onPress={restore} />
              </View>
            }
          />
        )}
        {items && items.length === 0 && (
          <View style={{ gap: 16, paddingVertical: 24 }}>
            <T v="heading">아직 저장한 문제가 없어요</T>
            <T muted>결과 화면에서 ‘기록에 저장’을 누르면 여기에 모여요.</T>
            <Button kind="primary" icon="camera" label="문제 사진 찍기" href="/" />
          </View>
        )}
        {group('오늘', today)}
        {group('이전', earlier)}
        {items && items.length > 0 && (
          <View style={{ alignItems: 'center' }}>
            <Button kind="danger" label="기록 모두 지우기" onPress={clearAll} />
          </View>
        )}
      </Page>
    </View>
  );
}
