// The photo being worked on, the latest result, and the on-device history.
// History never leaves the device (History.dc.html: 계정은 필요 없어요).
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';

import type { AudioStatus, FormalSpeech, Job, ProblemAudio } from './api';

export interface Picked {
  uri: string;
  width: number;
  height: number;
  mimeType: string;
  name: string;
  size?: number;
}

/** One reading of a problem: the sentence and its MP3. */
export interface Spoken {
  spokenText: string;
  // not_made: the formal reading before anyone asked for its MP3 (api.requestFormalAudio)
  audioStatus: AudioStatus | 'expired' | 'not_made';
  audioMessage: string;
  audioUrl: string | null;
}

/** 쉽게 (casual, the default: math as a person says it) or 정확하게 (formal: spelled out). */
export type ReadingStyle = 'casual' | 'formal';

/** One problem of a page with several: where it is on the photo, and its own audio. */
export interface Problem extends Spoken {
  label: string;
  boxes: [number, number, number, number][]; // fractions of the photo: x0, y0, x1, y1
  normalizedText: string;
  strictOk: boolean;
  formal?: Spoken; // the formal reading, when the backend made one
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
  audioStatus: Spoken['audioStatus'];
  audioMessage: string;
  audioUrl: string | null;
  formal?: Spoken; // the formal reading, when the backend made one
  problems?: Problem[]; // a page of numbered problems, read one at a time
}

/** The formal reading from a job's speech and audio entries, if there is one. */
function formalFrom(speech: FormalSpeech | undefined, audio: ProblemAudio | undefined): Spoken | undefined {
  if (!speech?.text) return undefined;
  const a = audio?.formal;
  return {
    spokenText: speech.text,
    // Its MP3 is made when the listener asks; one with a placeholder never is.
    audioStatus: a?.status ?? (speech.strict_ok && speech.ssml ? 'not_made' : 'skipped'),
    audioMessage: a?.message ?? '',
    audioUrl: a?.url ?? null,
  };
}

/** What to show and play for the chosen style: the formal reading where there is one. */
export function inStyle<T extends Spoken & { formal?: Spoken }>(x: T, style: ReadingStyle): T {
  return style === 'formal' && x.formal ? { ...x, ...x.formal } : x;
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

/** `r` with the formal MP3 that was just made, for the page (`problem` null) or problem index `problem`. */
export function withFormalAudio(r: Reading, problem: number | null, audio: Pick<Spoken, 'audioStatus' | 'audioMessage' | 'audioUrl'>): Reading {
  const set = <T extends { formal?: Spoken }>(x: T): T => (x.formal ? { ...x, formal: { ...x.formal, ...audio } } : x);
  if (problem == null) return set(r);
  return { ...r, problems: r.problems?.map((p, i) => (i === problem ? set(p) : p)) };
}

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
    formal: formalFrom(s.speech?.formal, job.audio),
    problems: s.problems?.map((p, i) => {
      const a = job.audio?.problems?.[i];
      return {
        label: p.label,
        boxes: p.boxes,
        normalizedText: p.normalized.text,
        spokenText: p.speech.text,
        strictOk: p.speech.strict_ok,
        audioStatus: a?.status ?? 'failed',
        audioMessage: a?.message ?? '',
        audioUrl: a?.url ?? null,
        formal: formalFrom(p.speech.formal, a),
      };
    }),
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

// A result's photo is the upload it came from: on web that is one data URL of
// a few MB, so it is stored once and the reading points at it.
const SAME_AS_UPLOAD = '@upload';
const SMALL_SIDE = 1280; // the stored copy of a photo too big for sessionStorage

/** Save the current flow. Call after changing `session`; fire and forget. */
export async function persistSession(): Promise<void> {
  const seq = ++persistSeq;
  try {
    const [picked, upload] = await Promise.all([durable(session.picked), durable(session.upload)]);
    if (seq !== persistSeq) return; // a newer call is writing
    const sent = session.upload?.uri;
    const readings = [...session.readings.values()]
      .slice(-SESSION_READINGS)
      .map((r) => (sent && r.imageUri === sent ? { ...r, imageUri: SAME_AS_UPLOAD } : r));
    const job = session.job;
    // Most useful first: if storage is full, drop the original photo (only the
    // crop screen needs it), then older results.
    const tries: (() => object | Promise<object>)[] = [
      () => ({ picked, upload, job, readings }),
      () => ({ picked: null, upload, job, readings }),
      () => ({ picked: null, upload, job, readings: readings.slice(-1) }),
      // A phone photo alone can be more than sessionStorage holds (about 5 MB,
      // less on Safari). A smaller copy keeps the photo on the result screen
      // after the browser reloads the page.
      async () => {
        const small = await smaller(upload);
        const last = readings.slice(-1).filter((r) => r.imageUri === SAME_AS_UPLOAD || !r.imageUri.startsWith('data:'));
        return { picked: null, upload: small, job, readings: last };
      },
    ];
    for (const snapshot of tries) {
      try {
        const value = JSON.stringify(await snapshot());
        if (seq !== persistSeq) return;
        await writeSession(value);
        return;
      } catch {
        // too big for storage: try the smaller snapshot
      }
    }
  } catch {
    // Storage unavailable: the flow still works, it just won't survive a refresh.
  }
}

/** Web: `p` re-encoded at SMALL_SIDE. Throws if that can't be done (then nothing smaller exists). */
async function smaller(p: Picked | null): Promise<Picked | null> {
  if (!p || Platform.OS !== 'web') throw new Error('no smaller copy');
  const { shrink } = await import('./image');
  const t = await shrink(p.uri, p.width, p.height, Math.min(SMALL_SIDE, Math.max(p.width, p.height)));
  return { ...p, uri: t.uri, width: t.width, height: t.height, size: t.size };
}

/** Load the saved flow into `session`. Run once, before the first screen. */
export async function restoreSession(): Promise<void> {
  try {
    const raw = await readSession();
    if (!raw) return;
    const s = JSON.parse(raw);
    const here = await relocator();
    const upload: Picked | null = s.upload ? { ...s.upload, uri: here(s.upload.uri) } : null;
    session.picked ??= s.picked ? { ...s.picked, uri: here(s.picked.uri) } : null;
    session.upload ??= upload;
    session.job ??= s.job ?? null;
    for (const stored of (s.readings ?? []) as Reading[]) {
      if (session.readings.has(stored.id)) continue;
      const r = relocated(stored, here);
      if (r.imageUri === SAME_AS_UPLOAD) {
        // the copy of the photo that was stored, which may be the smaller one
        r.imageUri = upload?.uri ?? '';
        r.imageWidth = upload?.width ?? 0;
        r.imageHeight = upload?.height ?? 0;
      }
      session.readings.set(r.id, r);
    }
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
  if (Date.now() - r.createdAt <= SERVER_RETENTION_MS) return r;
  const one = <T extends Pick<Spoken, 'audioUrl' | 'audioStatus'>>(x: T): T =>
    x.audioUrl?.startsWith('http') ? { ...x, audioStatus: 'expired', audioUrl: null } : x;
  const expire = <T extends Spoken & { formal?: Spoken }>(x: T): T => ({ ...one(x), formal: x.formal && one(x.formal) });
  return { ...expire(r), problems: r.problems?.map(expire) };
}

// iOS gives the app a new container path with every update, so a file URI
// stored by the previous install points nowhere: the photo and the MP3 are
// still there, under the new path. Native only; web URIs are left alone.
type Relocate = (uri: string) => string;
const asIs: Relocate = (uri) => uri;

async function relocator(): Promise<Relocate> {
  if (Platform.OS === 'web') return asIs;
  try {
    return (await import('./files')).relocate;
  } catch {
    return asIs;
  }
}

function relocated(r: Reading, here: Relocate): Reading {
  if (here === asIs) return { ...r };
  const audio = <T extends Spoken & { formal?: Spoken }>(x: T): T => ({
    ...x,
    audioUrl: x.audioUrl && here(x.audioUrl),
    formal: x.formal && { ...x.formal, audioUrl: x.formal.audioUrl && here(x.formal.audioUrl) },
  });
  return { ...audio(r), imageUri: here(r.imageUri), problems: r.problems?.map(audio) };
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
    const here = await relocator();
    return (await readHistory()).map((r) => withExpiry(relocated(r, here)));
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

const STYLE_KEY = 'mathtts.style';

export async function loadStyle(): Promise<ReadingStyle> {
  return (await AsyncStorage.getItem(STYLE_KEY)) === 'formal' ? 'formal' : 'casual';
}

export function storeStyle(v: ReadingStyle): void {
  AsyncStorage.setItem(STYLE_KEY, v).catch(() => {});
}
