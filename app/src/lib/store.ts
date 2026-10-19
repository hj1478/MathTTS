// The photo being worked on, the latest result, and the on-device history.
// History never leaves the device (History.dc.html: 계정은 필요 없어요).
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';

import type { AudioStatus, Job } from './api';

export interface Picked {
  uri: string;
  width: number;
  height: number;
  mimeType: string;
  name: string;
  size?: number;
}

/** What one finished job leaves behind, shown by the result screen. */
export interface Reading {
  id: string;
  createdAt: number; // ms
  imageUri: string; // the cropped photo that was sent
  imageWidth: number;
  imageHeight: number;
  ocrText: string;
  normalizedText: string;
  spokenText: string;
  strictOk: boolean;
  audioStatus: AudioStatus | 'expired';
  audioMessage: string;
  audioUrl: string | null;
}

// Module state for the current flow: home → crop → processing → result.
export const session: {
  picked: Picked | null; // as chosen, before cropping
  upload: Picked | null; // cropped, what POST /jobs gets
  readings: Map<string, Reading>; // finished this session, saved or not
} = { picked: null, upload: null, readings: new Map() };

export function readingFromJob(job: Job, upload: Picked): Reading {
  const s = job.stages ?? {};
  return {
    id: job.id,
    createdAt: job.created_at * 1000,
    imageUri: upload.uri,
    imageWidth: upload.width,
    imageHeight: upload.height,
    ocrText: s.ocr?.text ?? '',
    normalizedText: s.normalized?.text ?? s.ocr?.text ?? '',
    spokenText: s.speech?.text ?? '',
    strictOk: s.speech?.strict_ok ?? false,
    audioStatus: job.audio?.status ?? 'failed',
    audioMessage: job.audio?.message ?? '',
    audioUrl: job.audio?.url ?? null,
  };
}

// The server keeps audio for 24 h (docs/API.md, Retention).
const SERVER_RETENTION_MS = 24 * 3600 * 1000;
const KEY = 'mathtts.history.v1';
const WEB_MAX = 30; // localStorage holds ~5 MB; each entry carries a JPEG data URL

export async function listHistory(): Promise<Reading[]> {
  let items: Reading[] = [];
  try {
    items = JSON.parse((await AsyncStorage.getItem(KEY)) ?? '[]');
  } catch {
    items = [];
  }
  const now = Date.now();
  return items.map((r) =>
    r.audioUrl?.startsWith('http') && now - r.createdAt > SERVER_RETENTION_MS
      ? { ...r, audioStatus: 'expired', audioUrl: null }
      : r,
  );
}

export async function getReading(id: string): Promise<Reading | undefined> {
  return session.readings.get(id) ?? (await listHistory()).find((r) => r.id === id);
}

export async function isSaved(id: string): Promise<boolean> {
  return (await listHistory()).some((r) => r.id === id);
}

async function write(items: Reading[]) {
  await AsyncStorage.setItem(KEY, JSON.stringify(items));
}

export async function saveReading(r: Reading): Promise<void> {
  const items = (await listHistory()).filter((x) => x.id !== r.id);
  let kept = r;
  if (Platform.OS !== 'web') {
    const { keepFiles } = await import('./files');
    kept = await keepFiles(r);
  }
  items.unshift(kept);
  if (Platform.OS === 'web') items.splice(WEB_MAX);
  try {
    await write(items);
  } catch {
    // Storage full: drop the oldest half and try once more.
    items.splice(Math.max(1, Math.floor(items.length / 2)));
    await write(items);
  }
}

/** `keepFiles` leaves the photo and MP3 on disk so a 되돌리기 can restore them. */
export async function removeReading(id: string, opts?: { keepFiles?: boolean }): Promise<void> {
  const items = await listHistory();
  const gone = items.find((x) => x.id === id);
  await write(items.filter((x) => x.id !== id));
  if (gone && !opts?.keepFiles) await dropReadingFiles(gone);
}

export async function dropReadingFiles(r: Reading): Promise<void> {
  if (Platform.OS !== 'web') (await import('./files')).dropFiles(r);
}

export async function clearHistory(): Promise<void> {
  const items = await listHistory();
  await AsyncStorage.removeItem(KEY);
  if (Platform.OS !== 'web') {
    const { dropFiles } = await import('./files');
    items.forEach(dropFiles);
  }
}

const SPEED_KEY = 'mathtts.speed';

export async function loadSpeed(): Promise<number> {
  const v = Number(await AsyncStorage.getItem(SPEED_KEY));
  return [0.75, 1, 1.25].includes(v) ? v : 1;
}

export function storeSpeed(v: number): void {
  AsyncStorage.setItem(SPEED_KEY, String(v)).catch(() => {});
}
