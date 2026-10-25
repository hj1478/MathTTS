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
// Kept in storage too (persistSession), so a refresh or an app restart picks up
// where it was; restoreSession() runs before the first screen renders.
export const session: {
  picked: Picked | null; // as chosen, before cropping
  upload: Picked | null; // cropped, what POST /jobs gets
  job: { id: string; startedAt: number } | null; // the job for `upload`, once submitted
  readings: Map<string, Reading>; // finished this session, saved or not
} = { picked: null, upload: null, job: null, readings: new Map() };

/** `upload` is null when the job was opened by link, without its photo. */
export function readingFromJob(job: Job, upload: Picked | null): Reading {
  const s = job.stages ?? {};
  return {
    id: job.id,
    createdAt: job.created_at * 1000,
    imageUri: upload?.uri ?? '',
    imageWidth: upload?.width ?? 0,
    imageHeight: upload?.height ?? 0,
    ocrText: s.ocr?.text ?? '',
    normalizedText: s.normalized?.text ?? s.ocr?.text ?? '',
    spokenText: s.speech?.text ?? '',
    strictOk: s.speech?.strict_ok ?? false,
    audioStatus: job.audio?.status ?? 'failed',
    audioMessage: job.audio?.message ?? '',
    audioUrl: job.audio?.url ?? null,
  };
}

// --- the current flow, across a refresh ----------------------------------------
// Web: sessionStorage, so it belongs to this tab and goes when the tab closes.
// Native: AsyncStorage (file URIs in the cache, so only the strings are stored).
const SESSION_KEY = 'mathtts.session.v1';
const SESSION_READINGS = 3; // unsaved results kept; each carries a JPEG data URL on web

const sessionStorageOrNull = (): Storage | null => {
  try {
    return typeof window !== 'undefined' ? window.sessionStorage : null;
  } catch {
    return null; // blocked (privacy settings)
  }
};

async function readSession(): Promise<string | null> {
  if (Platform.OS !== 'web') return AsyncStorage.getItem(SESSION_KEY);
  return sessionStorageOrNull()?.getItem(SESSION_KEY) ?? null;
}

async function writeSession(value: string): Promise<void> {
  if (Platform.OS !== 'web') return AsyncStorage.setItem(SESSION_KEY, value);
  sessionStorageOrNull()?.setItem(SESSION_KEY, value); // throws when full
}

/** A picked file on web is a blob: URL, which dies with the page; store its bytes. */
async function durable(p: Picked | null): Promise<Picked | null> {
  if (!p || Platform.OS !== 'web' || !p.uri.startsWith('blob:')) return p;
  const blob = await (await fetch(p.uri)).blob();
  const uri = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
  return { ...p, uri };
}

let persistSeq = 0;

/** Save the current flow. Call after changing `session`; fire and forget. */
export async function persistSession(): Promise<void> {
  const seq = ++persistSeq;
  try {
    const [picked, upload] = await Promise.all([durable(session.picked), durable(session.upload)]);
    if (seq !== persistSeq) return; // a newer call is writing
    const readings = [...session.readings.values()].slice(-SESSION_READINGS);
    // Most useful first: if storage is full, drop the original photo (only the
    // crop screen needs it), then older results.
    const tries = [
      { picked, upload, job: session.job, readings },
      { picked: null, upload, job: session.job, readings },
      { picked: null, upload, job: session.job, readings: readings.slice(-1) },
    ];
    for (const snapshot of tries) {
      try {
        await writeSession(JSON.stringify(snapshot));
        return;
      } catch {
        // too big for storage: try the smaller snapshot
      }
    }
  } catch {
    // Storage unavailable: the flow still works, it just won't survive a refresh.
  }
}

/** Load the saved flow into `session`. Run once, before the first screen. */
export async function restoreSession(): Promise<void> {
  try {
    const raw = await readSession();
    if (!raw) return;
    const s = JSON.parse(raw);
    session.picked ??= s.picked ?? null;
    session.upload ??= s.upload ?? null;
    session.job ??= s.job ?? null;
    for (const r of (s.readings ?? []) as Reading[]) if (!session.readings.has(r.id)) session.readings.set(r.id, r);
  } catch {
    // Nothing usable saved.
  }
}

// The server keeps audio for 24 h (docs/API.md, Retention).
const SERVER_RETENTION_MS = 24 * 3600 * 1000;
const KEY = 'mathtts.history.v1';
const WEB_MAX = 30; // localStorage holds ~5 MB; each entry carries a JPEG thumbnail
// Native history is one AsyncStorage row, and Android can't read a row past
// ~2 MB; an entry is a few KB (the photo and MP3 are files), so this stays far under.
const NATIVE_MAX = 200;
const THUMB_SIDE = 800; // web history keeps a smaller copy of the photo, still legible zoomed

/** A remote MP3 the server has already deleted can't play; say so instead. */
export function withExpiry(r: Reading): Reading {
  return r.audioUrl?.startsWith('http') && Date.now() - r.createdAt > SERVER_RETENTION_MS
    ? { ...r, audioStatus: 'expired', audioUrl: null }
    : r;
}

// The last parse, reused while the stored text is unchanged (the home screen
// reads history on every focus). Compared by text, so other tabs' writes count.
let parsed: { raw: string; items: Reading[] } | null = null;

/** Throws if the saved list can't be read, so a caller never writes over it. */
async function readHistory(): Promise<Reading[]> {
  const raw = await AsyncStorage.getItem(KEY);
  if (raw == null) return [];
  if (parsed?.raw !== raw) {
    const items = JSON.parse(raw);
    if (!Array.isArray(items)) throw new Error('history is not a list');
    parsed = { raw, items };
  }
  return [...parsed.items];
}

/** For showing: an unreadable list shows as empty (and is left alone). */
export async function listHistory(): Promise<Reading[]> {
  try {
    return (await readHistory()).map(withExpiry);
  } catch {
    return [];
  }
}

/** The saved copy first: it has the on-device files, the session copy may not. */
export async function getReading(id: string): Promise<Reading | undefined> {
  const saved = (await listHistory()).find((r) => r.id === id);
  const current = session.readings.get(id);
  return saved ?? (current && withExpiry(current));
}

export async function isSaved(id: string): Promise<boolean> {
  return (await listHistory()).some((r) => r.id === id);
}

async function write(items: Reading[]) {
  await AsyncStorage.setItem(KEY, JSON.stringify(items));
}

/** Web: shrink a data-URL photo to THUMB_SIDE so ~30 fit in localStorage. */
async function thumbnail(r: Reading): Promise<Reading> {
  if (!r.imageUri.startsWith('data:') || Math.max(r.imageWidth, r.imageHeight) <= THUMB_SIDE) return r;
  try {
    const { shrink } = await import('./image');
    const t = await shrink(r.imageUri, r.imageWidth, r.imageHeight, THUMB_SIDE);
    return { ...r, imageUri: t.uri, imageWidth: t.width, imageHeight: t.height };
  } catch {
    return r; // keep the full photo; the write below trims if it doesn't fit
  }
}

export async function saveReading(r: Reading): Promise<void> {
  const items = (await readHistory()).filter((x) => x.id !== r.id);
  let kept = r;
  if (Platform.OS !== 'web') {
    const { keepFiles } = await import('./files');
    kept = await keepFiles(r);
  } else {
    kept = await thumbnail(r);
  }
  items.unshift(kept);
  const dropped = items.splice(Platform.OS === 'web' ? WEB_MAX : NATIVE_MAX);
  // Storage full: drop the oldest entries, one at a time, until it fits.
  for (;;) {
    try {
      await write(items);
      break;
    } catch (e) {
      if (items.length <= 1) throw e;
      dropped.push(...items.splice(-1));
    }
  }
  dropped.forEach(dropReadingFiles);
}

/** `keepFiles` leaves the photo and MP3 on disk so a 되돌리기 can restore them. */
export async function removeReading(id: string, opts?: { keepFiles?: boolean }): Promise<void> {
  const items = await readHistory();
  const gone = items.find((x) => x.id === id);
  await write(items.filter((x) => x.id !== id));
  if (gone && !opts?.keepFiles) await dropReadingFiles(gone);
}

export async function dropReadingFiles(r: Reading): Promise<void> {
  if (Platform.OS !== 'web') (await import('./files')).dropFiles(r);
}

/** Native: delete photo/MP3 folders no saved entry points at (an app killed
 * during the 되돌리기 window, an older trim). Run once at startup. */
export async function dropOrphanFiles(): Promise<void> {
  if (Platform.OS === 'web') return;
  try {
    const items = await readHistory();
    (await import('./files')).dropFilesExcept(new Set(items.map((r) => r.id)));
  } catch {
    // History unreadable: keep every file.
  }
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
